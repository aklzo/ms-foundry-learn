"""APIM ポリシー(方式 A)のオフライン・エミュレーター — ``infra/apim/policies/*.xml`` を直接読んで判定する。

目的は「ポリシーファイルそのものをテストする」こと。宛先・発行者・必須クレームは Python 側に
書き写さず、XML から読み取った値だけで ``validate-jwt`` を再現する。XML を書き換えれば判定も変わり、
書き換えを忘れればテストが落ちる(テスト側でファイルを改変して確かめている)。

対応している範囲(これ以外の要素・属性・ポリシー式があれば **読み込み時に例外** にして、
黙って無視したまま緑になる事故を防ぐ):

- ``<inbound>``: ``<base />``(上位スコープ。エミュレートしない)、``<validate-jwt>``、
  固定値(Named Value を含む)の ``<set-header>``(``exists-action`` = override / skip / delete)
  - 属性: ``id`` / ``header-name`` / ``require-scheme`` / ``failed-validation-httpcode`` /
    ``failed-validation-error-message`` / ``require-expiration-time`` / ``require-signed-tokens`` /
    ``clock-skew``(整数秒)/ ``output-token-variable-name``(無視)
  - 子要素: ``openid-config``(JWKS と発行者を取得)/ ``audiences`` / ``issuers`` /
    ``required-claims``(``match="all|any"``・``separator``)
- ``<backend>`` / ``<outbound>``: ``<base />`` のみ(= そのまま転送。応答本文に触れない)
- ``<on-error>``: ``<base />`` と、``<choose><when condition='@(context.LastError.PolicyId == "x")'>``
  の中の固定値 ``<set-header>`` のみ
- Named Values(二重波かっこ参照)は ``named_values`` で置き換える(不足は例外)。
  ゲートウェイの秘密(``dah-gateway-secret``)もこの経路で入り、ログ・repr には出さない
- 失敗時の応答は APIM と同じ形の本文 ``{"statusCode": ..., "message": ...}``

**エミュレーターでは証明できないこと**(README・runbook に同じ内容を書く):

- 実際の APIM がこの XML を受け付けるか(スキーマ・Named Values の解決・Bicep の ``rawxml``)
- C# のポリシー式の評価(条件式は上の 1 パターンだけを文字列として解釈している)
- 実 Entra トークンでのクレーム照合の細部(``scp`` の区切り文字、``roles`` 配列の扱い)と
  APIM 独自の既定値(``clock-skew`` 既定 0 秒、OpenID 設定のキャッシュ間隔 1 時間・再取得 5 分)
- 上位スコープ(グローバル・製品)のポリシー、サブスクリプションキー、レート制限
- ネットワーク経路そのもの(迂回はゲートウェイの秘密ヘッダーでサーバーが拒否する。秘密が漏れれば
  迂回できるので、実環境では秘密 Named Value・Container Apps のシークレット・トレース設定の管理が前提)
- 秘密の Named Value がトレース(APIM の要求トレース・診断ログのヘッダー記録)に出ないこと
- 応答ヘッダー・本文の細部、レイテンシ、Consumption 階層のコールドスタート
"""

from __future__ import annotations

import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import jwt
from jwt import PyJWK
from starlette.types import ASGIApp, Receive, Scope, Send

from ..contracts import MCP_SERVERS, McpServerSpec
from .settings import DEFAULT_POLICIES_DIR

logger = logging.getLogger("delegated_access_maf.tools_server.apim_emulator")

#: validate-jwt が受け付ける非対称アルゴリズム(公式リファレンスの一覧)
_ALGORITHMS = ["RS256", "RS512", "PS256", "ES256"]
_NAMED_VALUE = re.compile(r"\{\{([A-Za-z0-9._-]+)\}\}")
_POLICY_ID_CONDITION = re.compile(r'^@\(\s*context\.LastError\.PolicyId\s*==\s*"([^"]+)"\s*\)$')
_JWT_ATTRS = {
    "id",
    "header-name",
    "require-scheme",
    "failed-validation-httpcode",
    "failed-validation-error-message",
    "require-expiration-time",
    "require-signed-tokens",
    "clock-skew",
    "output-token-variable-name",
}


class UnsupportedPolicyError(ValueError):
    """エミュレーターが解釈できないポリシー(黙って無視しない)。"""


# --- ポリシーのモデル ------------------------------------------------------------------


@dataclass(frozen=True)
class ClaimRequirement:
    name: str
    values: tuple[str, ...]
    match: str = "all"
    separator: str | None = None


@dataclass(frozen=True)
class ValidateJwt:
    id: str | None
    header_name: str
    require_scheme: str | None
    failed_status: int
    failed_message: str | None
    require_expiration_time: bool
    require_signed_tokens: bool
    clock_skew: int
    openid_config_urls: tuple[str, ...]
    audiences: tuple[str, ...]
    issuers: tuple[str, ...]
    required_claims: tuple[ClaimRequirement, ...]


@dataclass(frozen=True)
class OnErrorHeader:
    """``<when condition='@(context.LastError.PolicyId == "x")'>`` の中の固定値 set-header。"""

    policy_id: str
    name: str
    value: str
    exists_action: str = "override"


@dataclass(frozen=True)
class SetHeader:
    """inbound の固定値 set-header(値は秘密を含みうるので repr に出さない)。"""

    name: str
    value: str = field(repr=False)
    exists_action: str = "override"


@dataclass(frozen=True)
class ApiPolicy:
    name: str
    inbound: tuple[ValidateJwt | SetHeader, ...]
    on_error: tuple[OnErrorHeader, ...]

    @property
    def jwt_steps(self) -> tuple[ValidateJwt, ...]:
        return tuple(s for s in self.inbound if isinstance(s, ValidateJwt))

    @property
    def set_headers(self) -> tuple[SetHeader, ...]:
        return tuple(s for s in self.inbound if isinstance(s, SetHeader))


@dataclass(frozen=True)
class LastError:
    """APIM の ``context.LastError`` 相当。"""

    source: str
    reason: str
    message: str
    policy_id: str | None


@dataclass(frozen=True)
class GatewayDecision:
    api: str
    status: int
    reason: str
    policy_id: str | None = None
    at: float = field(default_factory=time.time)


# --- XML の読み込み --------------------------------------------------------------------


def _bool_attr(el: ET.Element, name: str, default: bool) -> bool:
    raw = el.get(name)
    if raw is None:
        return default
    if raw.lower() not in ("true", "false"):
        raise UnsupportedPolicyError(f"{name}={raw!r} must be true or false")
    return raw.lower() == "true"


def _no_expression(value: str, where: str) -> str:
    if value.strip().startswith("@"):
        raise UnsupportedPolicyError(f"policy expressions are not emulated ({where}: {value!r})")
    return value.strip()


def _parse_validate_jwt(el: ET.Element) -> ValidateJwt:
    unknown = set(el.attrib) - _JWT_ATTRS
    if unknown:
        raise UnsupportedPolicyError(f"validate-jwt attribute(s) not emulated: {sorted(unknown)}")
    for name, value in el.attrib.items():
        _no_expression(value, f"validate-jwt@{name}")
    header_name = el.get("header-name")
    if not header_name:
        raise UnsupportedPolicyError(
            "validate-jwt needs header-name (query/token-value not emulated)"
        )

    urls: list[str] = []
    audiences: list[str] = []
    issuers: list[str] = []
    claims: list[ClaimRequirement] = []
    for child in el:
        if not isinstance(child.tag, str):  # コメント
            continue
        if child.tag == "openid-config":
            urls.append(_no_expression(child.get("url", ""), "openid-config@url"))
        elif child.tag == "audiences":
            audiences += [
                _no_expression(a.text or "", "audience") for a in child if a.tag == "audience"
            ]
        elif child.tag == "issuers":
            issuers += [_no_expression(i.text or "", "issuer") for i in child if i.tag == "issuer"]
        elif child.tag == "required-claims":
            for c in child:
                if not isinstance(c.tag, str):
                    continue
                if c.tag != "claim":
                    raise UnsupportedPolicyError(f"unexpected element in required-claims: {c.tag}")
                match = c.get("match", "all")
                if match not in ("all", "any"):
                    raise UnsupportedPolicyError(f"claim match={match!r}")
                values = tuple(
                    _no_expression(v.text or "", "claim value") for v in c if v.tag == "value"
                )
                claims.append(
                    ClaimRequirement(
                        name=c.get("name", ""),
                        values=values,
                        match=match,
                        separator=c.get("separator"),
                    )
                )
        else:
            raise UnsupportedPolicyError(f"validate-jwt child not emulated: <{child.tag}>")
    if not urls:
        raise UnsupportedPolicyError("validate-jwt without openid-config is not emulated")

    if not _bool_attr(el, "require-signed-tokens", True):
        raise UnsupportedPolicyError("require-signed-tokens=false is not emulated")
    skew_raw = el.get("clock-skew", "0")
    if not skew_raw.isdigit():
        raise UnsupportedPolicyError(f"clock-skew={skew_raw!r} (only integer seconds are emulated)")
    return ValidateJwt(
        id=el.get("id"),
        header_name=header_name,
        require_scheme=el.get("require-scheme"),
        failed_status=int(el.get("failed-validation-httpcode", "401")),
        failed_message=el.get("failed-validation-error-message"),
        require_expiration_time=_bool_attr(el, "require-expiration-time", True),
        require_signed_tokens=_bool_attr(el, "require-signed-tokens", True),
        clock_skew=int(skew_raw),
        openid_config_urls=tuple(urls),
        audiences=tuple(audiences),
        issuers=tuple(issuers),
        required_claims=tuple(claims),
    )


def _parse_set_header(el: ET.Element) -> SetHeader:
    unknown = set(el.attrib) - {"name", "exists-action"}
    if unknown:
        raise UnsupportedPolicyError(f"set-header attribute(s) not emulated: {sorted(unknown)}")
    name = _no_expression(el.get("name", ""), "set-header@name")
    action = el.get("exists-action", "override")
    if not name or action not in ("override", "skip", "delete"):
        raise UnsupportedPolicyError(f"set-header name={name!r} exists-action={action!r}")
    values = [v for v in el if isinstance(v.tag, str)]
    if action == "delete":
        if values:
            raise UnsupportedPolicyError("set-header delete takes no <value>")
        return SetHeader(name=name, value="", exists_action=action)
    if len(values) != 1 or values[0].tag != "value":
        raise UnsupportedPolicyError("set-header needs exactly one <value>")
    return SetHeader(
        name=name,
        value=_no_expression(values[0].text or "", "set-header value"),
        exists_action=action,
    )


def _apply_set_header(
    headers: list[tuple[bytes, bytes]], step: SetHeader
) -> list[tuple[bytes, bytes]]:
    key = step.name.lower().encode("latin-1")
    exists = any(n == key for n, _ in headers)
    if step.exists_action == "skip" and exists:
        return headers
    kept = [(n, v) for n, v in headers if n != key]  # override / delete は既存の同名ヘッダーを消す
    if step.exists_action == "delete":
        return kept
    return [*kept, (key, step.value.encode("latin-1"))]


def _only_base(section: ET.Element | None, name: str) -> None:
    if section is None:
        return
    for child in section:
        if isinstance(child.tag, str) and child.tag != "base":
            raise UnsupportedPolicyError(
                f"<{name}> may only contain <base /> (found <{child.tag}>)"
            )


def _parse_on_error(section: ET.Element | None) -> tuple[OnErrorHeader, ...]:
    rules: list[OnErrorHeader] = []
    if section is None:
        return ()
    for child in section:
        if not isinstance(child.tag, str) or child.tag == "base":
            continue
        if child.tag != "choose":
            raise UnsupportedPolicyError(f"<on-error> child not emulated: <{child.tag}>")
        for when in child:
            if not isinstance(when.tag, str):
                continue
            if when.tag != "when":
                raise UnsupportedPolicyError(f"<choose> child not emulated: <{when.tag}>")
            m = _POLICY_ID_CONDITION.match(when.get("condition", "").strip())
            if not m:
                raise UnsupportedPolicyError(
                    f"condition not emulated: {when.get('condition')!r} "
                    '(only @(context.LastError.PolicyId == "<id>"))'
                )
            for action in when:
                if not isinstance(action.tag, str):
                    continue
                if action.tag != "set-header":
                    raise UnsupportedPolicyError(f"<when> child not emulated: <{action.tag}>")
                values = [v for v in action if v.tag == "value"]
                if len(values) != 1:
                    raise UnsupportedPolicyError("set-header needs exactly one <value>")
                rules.append(
                    OnErrorHeader(
                        policy_id=m.group(1),
                        name=action.get("name", ""),
                        value=_no_expression(values[0].text or "", "set-header value"),
                        exists_action=action.get("exists-action", "override"),
                    )
                )
    return tuple(rules)


def substitute_named_values(text: str, named_values: Mapping[str, str]) -> str:
    """APIM の Named Values 参照を置き換える。未定義の名前は APIM と同じく失敗にする。"""

    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in named_values:
            raise UnsupportedPolicyError(f"named value {key!r} is not defined")
        return named_values[key]

    return _NAMED_VALUE.sub(repl, text)


def parse_policy(xml_text: str, *, name: str, named_values: Mapping[str, str]) -> ApiPolicy:
    root = ET.fromstring(substitute_named_values(xml_text, named_values))
    if root.tag != "policies":
        raise UnsupportedPolicyError(f"root element must be <policies> (found <{root.tag}>)")
    known = {"inbound", "backend", "outbound", "on-error"}
    for child in root:
        if isinstance(child.tag, str) and child.tag not in known:
            raise UnsupportedPolicyError(f"unknown section <{child.tag}>")
    inbound: list[ValidateJwt | SetHeader] = []
    section = root.find("inbound")
    if section is not None:
        for child in section:
            if not isinstance(child.tag, str) or child.tag == "base":
                continue
            if child.tag == "validate-jwt":
                inbound.append(_parse_validate_jwt(child))
            elif child.tag == "set-header":
                inbound.append(_parse_set_header(child))
            else:
                raise UnsupportedPolicyError(f"<inbound> policy not emulated: <{child.tag}>")
    _only_base(root.find("backend"), "backend")
    _only_base(root.find("outbound"), "outbound")
    return ApiPolicy(
        name=name, inbound=tuple(inbound), on_error=_parse_on_error(root.find("on-error"))
    )


def load_policies(
    named_values: Mapping[str, str],
    *,
    policies_dir: Path = DEFAULT_POLICIES_DIR,
    apis: Sequence[McpServerSpec] = MCP_SERVERS,
) -> dict[str, ApiPolicy]:
    """``<policies_dir>/<spec.name>.xml`` を API ごとに読む(ファイルがない API は例外)。"""
    return {
        spec.name: parse_policy(
            (policies_dir / f"{spec.name}.xml").read_text(encoding="utf-8"),
            name=spec.name,
            named_values=named_values,
        )
        for spec in apis
    }


def named_values_for(tenant_id: str, tools_client_id: str, gateway_secret: str) -> dict[str, str]:
    """Bicep が作る Named Values と同じ名前・値(infra/modules/apim.bicep と揃える)。

    ``dah-gateway-secret`` は秘密の Named Value(ツールサーバーの ``APIM_GATEWAY_SECRET`` と同じ値)。
    """
    return {
        "dah-tenant-id": tenant_id,
        "dah-tools-api-client-id": tools_client_id,
        "dah-gateway-secret": gateway_secret,
    }


# --- validate-jwt の実行 ---------------------------------------------------------------


class _Failure(Exception):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


class _OpenIdCache:
    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http = http_client
        self._issuers: dict[str, str] = {}
        self._keys: dict[str, dict[str, PyJWK]] = {}

    async def _refresh(self, url: str) -> None:
        meta = (await self._http.get(url)).raise_for_status().json()
        jwks = (await self._http.get(meta["jwks_uri"])).raise_for_status().json()
        self._issuers[url] = meta.get("issuer", "")
        self._keys[url] = {k["kid"]: PyJWK(k) for k in jwks.get("keys", []) if "kid" in k}

    async def key(self, url: str, kid: str) -> PyJWK | None:
        if kid not in self._keys.get(url, {}):
            await self._refresh(url)  # 未知の kid は 1 回だけ取り直す(鍵のロールオーバー)
        return self._keys[url].get(kid)

    def issuer(self, url: str) -> str:
        return self._issuers.get(url, "")


def _claim_values(value: Any, separator: str | None) -> set[str]:
    if isinstance(value, list):
        return {str(v) for v in value}
    text = str(value)
    if separator:
        return {v for v in text.split(separator) if v}
    return {text}


async def _run_validate_jwt(
    policy: ValidateJwt, headers: Mapping[str, str], oidc: _OpenIdCache
) -> None:
    raw = headers.get(policy.header_name.lower())
    if not raw:
        raise _Failure("TokenNotPresent", "JWT not present.")
    token = raw.strip()
    if policy.require_scheme:
        scheme, _, rest = token.partition(" ")
        if scheme.lower() != policy.require_scheme.lower() or not rest.strip():
            raise _Failure("TokenNotPresent", "JWT not present.")
        token = rest.strip()

    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as ex:
        raise _Failure("JwtInvalid", str(ex)) from ex
    alg = header.get("alg", "none")
    if alg not in _ALGORITHMS:  # 署名なし(alg=none)や対称鍵は受け付けない
        raise _Failure("TokenSignatureInvalid", f"unsupported alg {alg}. Access denied.")

    key: PyJWK | None = None
    url_used = ""
    for url in policy.openid_config_urls:
        key = await oidc.key(url, header.get("kid", ""))
        if key is not None:
            url_used = url
            break
    if key is None:
        raise _Failure("TokenSignatureKeyNotFound", "signing key not found. Access denied.")

    try:
        claims = jwt.decode(
            token,
            key.key,
            algorithms=_ALGORITHMS,
            leeway=policy.clock_skew,
            options={
                "verify_aud": False,  # 宛先・発行者は下で XML の値と照合し、APIM と同じ理由コードにする
                "verify_iss": False,
                "require": ["exp"] if policy.require_expiration_time else [],
            },
        )
    except jwt.ExpiredSignatureError as ex:
        raise _Failure("TokenExpired", f"{ex}. Access denied.") from ex
    except jwt.InvalidSignatureError as ex:
        raise _Failure("TokenSignatureInvalid", f"{ex}. Access denied.") from ex
    except jwt.PyJWTError as ex:
        raise _Failure("JwtInvalid", str(ex)) from ex

    if policy.audiences:
        aud = claims.get("aud")
        auds = set(aud) if isinstance(aud, list) else {aud}
        if not auds.intersection(policy.audiences):
            raise _Failure("TokenAudienceNotAllowed", "audience not allowed. Access denied.")
    issuers = policy.issuers or (oidc.issuer(url_used),)
    if claims.get("iss") not in issuers:
        raise _Failure("TokenIssuerNotAllowed", "issuer not allowed. Access denied.")

    missing = [c.name for c in policy.required_claims if c.name not in claims]
    if missing:
        raise _Failure(
            "TokenClaimNotFound",
            f"JWT is missing the following claims: {', '.join(missing)}. Access denied.",
        )
    for c in policy.required_claims:
        present = _claim_values(claims[c.name], c.separator)
        ok = (
            all(v in present for v in c.values)
            if c.match == "all"
            else any(v in present for v in c.values)
        )
        if not ok:
            raise _Failure(
                "TokenClaimValueNotAllowed", f"Claim {c.name} value is not allowed. Access denied."
            )


# --- ASGI ミドルウェア(ゲートウェイ役)------------------------------------------------


class ApimEmulator:
    """ツールサーバーの前に置く疑似 APIM。API = 契約パス、オペレーション = ``POST <path>``。

    判定に通ったリクエストはヘッダー(Authorization を含む)も本文もそのまま転送する。
    ``decisions`` に API ごとの判定を残す(テスト用)。
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        named_values: Mapping[str, str],
        http_client: httpx.AsyncClient,
        policies: Mapping[str, ApiPolicy] | None = None,
        policies_dir: Path = DEFAULT_POLICIES_DIR,
        apis: Sequence[McpServerSpec] = MCP_SERVERS,
        methods: Sequence[str] = ("POST",),
    ) -> None:
        self.app = app
        self.apis = tuple(apis)
        self.policies = (
            dict(policies)
            if policies is not None
            else load_policies(named_values, policies_dir=policies_dir, apis=apis)
        )
        missing = [s.name for s in self.apis if s.name not in self.policies]
        if missing:
            raise UnsupportedPolicyError(f"no policy for API(s): {missing}")
        self.methods = {m.upper() for m in methods}
        self.decisions: list[GatewayDecision] = []
        self._oidc = _OpenIdCache(http_client)

    def _match(self, path: str) -> McpServerSpec | None:
        return next((s for s in self.apis if path == s.path), None)

    async def _respond(
        self, send: Send, status: int, message: str, extra_headers: Sequence[tuple[str, str]] = ()
    ) -> None:
        body = json.dumps({"statusCode": status, "message": message}).encode()
        headers = [
            (b"content-type", b"application/json; charset=utf-8"),
            (b"content-length", str(len(body)).encode()),
        ] + [(k.lower().encode(), v.encode()) for k, v in extra_headers]
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)  # lifespan はツールサーバーへ
            return
        spec = self._match(scope.get("path", ""))
        if spec is None or scope.get("method", "").upper() not in self.methods:
            # APIM は API / オペレーションに一致しない要求を 404 で返す(バックエンドに届かない)
            self.decisions.append(GatewayDecision(api="-", status=404, reason="OperationNotFound"))
            await self._respond(send, 404, "Resource not found")
            return

        policy = self.policies[spec.name]
        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])
        }
        forwarded: list[tuple[bytes, bytes]] = list(scope.get("headers", []))
        for step in policy.inbound:
            if isinstance(step, SetHeader):
                # バックエンド向けの要求だけを変える(判定に使う受信ヘッダーは変えない)
                forwarded = _apply_set_header(forwarded, step)
                continue
            try:
                await _run_validate_jwt(step, headers, self._oidc)
            except _Failure as failure:
                error = LastError("validate-jwt", failure.reason, failure.message, step.id)
                self.decisions.append(
                    GatewayDecision(spec.name, step.failed_status, failure.reason, step.id)
                )
                logger.warning(
                    "apim_emulator deny api=%s policy=%s reason=%s",
                    spec.name,
                    step.id,
                    failure.reason,
                )
                extra = [
                    (rule.name, rule.value)
                    for rule in policy.on_error
                    if rule.policy_id == error.policy_id
                ]
                await self._respond(
                    send, step.failed_status, step.failed_message or failure.message, extra
                )
                return
        self.decisions.append(GatewayDecision(spec.name, 200, "forwarded"))
        await self.app({**scope, "headers": forwarded}, receive, send)

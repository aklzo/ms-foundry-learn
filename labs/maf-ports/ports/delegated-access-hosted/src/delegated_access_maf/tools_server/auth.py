"""MCP エンドポイントごとの認可ミドルウェア(方式 B の最終判定点)と、検証済み呼び出し元の受け渡し。

判定の置き場所は ``EnforcementMode`` で切り替える:

======================  ==============================  ==============================
判定内容                 ``server``(方式 B)              ``apim``(方式 A)
======================  ==============================  ==============================
APIM を経由したか         (見ない)                         サーバー(403: ゲートウェイの秘密)
署名・発行者・宛先・期限   サーバー(401)                   APIM(401)+ サーバーも再検証(401)
委任トークンか(app-only) サーバー(403)                   APIM(403: scp クレーム必須)
スコープ Tools.Access     サーバー(403)                   APIM(403)
エンドポイントのロール     サーバー(403)                   APIM(403)。サーバーは見ない
文書の権限絞り込み         ツール内(両方式共通)             ツール内(両方式共通)
======================  ==============================  ==============================

``apim`` でもサーバーが署名を検証するのは多層防御と、文書の絞り込みに使うロールを
「検証済みトークンから」読むため。ロールでの門番はサーバーではしないので、APIM を迂回されると
更新系にも届いてしまう。APIM Consumption は VNet に入れられず、ツールサーバーの受信経路を
APIM に限定できないため、``apim`` 方式では **ゲートウェイの秘密** で迂回を塞ぐ:

- APIM のポリシーが秘密の Named Value ``dah-gateway-secret`` をヘッダー
  ``x-apim-gateway-secret``(``contracts.APIM_GATEWAY_SECRET_HEADER``)に上書きで付ける
  (validate-jwt 2 段の後。利用者が同名ヘッダーを送っても APIM が上書きする)
- サーバーは環境変数 ``APIM_GATEWAY_SECRET`` と **定数時間で比較** し、欠落・不一致は 403
  (本文は汎用。ログの理由は ``gateway_secret_mismatch``)。トークンの検証より先に判定するので、
  迂回した呼び出しは JWKS の取得すら起こさない
- 比較後はヘッダーを取り除いてから MCP へ渡す(ツールや MCP の Request に秘密を残さない)。
  値はログ・判定記録・例外に一切出さない

より強い代替: APIM の ``authentication-managed-identity`` ポリシーで APIM のマネージド ID の
トークンを取り、別ヘッダー(Authorization は利用者のトークンなので使えない)でバックエンドへ送って、
サーバーが JwtValidator で検証する方式。共有の秘密(ローテーション・漏えい管理)が不要になり、
「どの APIM か」を署名で確かめられる。本ラボは構成の単純さを優先して共有の秘密にしている。

検証済みの ``Principal`` はリクエストの ``scope["state"]`` に入れ、ツール関数は
``principal_from(ctx)`` で取り出す(MCP の Context → Starlette の Request → state)。
トークン文字列そのものはどこにも保存しない。
"""

from __future__ import annotations

import hmac
import json
import logging
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from mcp.server.fastmcp import Context
from starlette.types import ASGIApp, Receive, Scope, Send

from ..contracts import (
    APIM_GATEWAY_SECRET_HEADER,
    TOOLS_API_SCOPE_NAME,
    EnforcementMode,
    McpServerSpec,
)
from ..jwt_validation import JwtValidator, Principal, TokenError

logger = logging.getLogger("delegated_access_maf.tools_server.auth")

PRINCIPAL_STATE_KEY = "principal"
_GATEWAY_HEADER = APIM_GATEWAY_SECRET_HEADER.encode("latin-1")
GATEWAY_SECRET_MISMATCH = "gateway_secret_mismatch"

#: 応答本文と WWW-Authenticate は汎用文言だけ(どのロールが足りないかは利用者に返さずログに残す)
_MISSING_TOKEN_CHALLENGE = (
    'Bearer error="invalid_token", error_description="the access token is missing"'
)
_FORBIDDEN_CHALLENGE = (
    'Bearer error="insufficient_scope", '
    'error_description="the access token does not grant access to this endpoint"'
)


@dataclass(frozen=True)
class AuthDecision:
    """1 リクエスト分の認可判定(監査用。トークンは含めない)。"""

    server: str
    mode: EnforcementMode
    decision: str  # "allow" | "deny"
    status: int
    reason: str
    oid: str | None = None
    upn: str | None = None
    at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class AuthDecisionLog:
    """直近の判定をメモリに保持し、同じ内容を構造化ログにも出す。"""

    def __init__(self, maxlen: int = 1000) -> None:
        self._items: deque[AuthDecision] = deque(maxlen=maxlen)

    def record(self, decision: AuthDecision) -> None:
        self._items.append(decision)
        level = logging.INFO if decision.decision == "allow" else logging.WARNING
        logger.log(level, "mcp_auth %s", json.dumps(asdict(decision), ensure_ascii=False))

    def items(self) -> list[AuthDecision]:
        return list(self._items)


def principal_from(ctx: Context) -> Principal:
    """ツール関数から検証済みの呼び出し元を取り出す。ミドルウェアを通っていなければ例外。"""
    request = ctx.request_context.request
    principal = None
    if request is not None:
        principal = request.scope.get("state", {}).get(PRINCIPAL_STATE_KEY)
    if not isinstance(principal, Principal):
        # ミドルウェアの付け忘れを「全社員扱い」で素通りさせない
        raise PermissionError("no validated principal on this request")
    return principal


def _bearer_token(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name == b"authorization":
            scheme, _, token = value.decode("latin-1").partition(" ")
            if scheme.lower() == "bearer" and token.strip():
                return token.strip()
            return None
    return None


def _take_gateway_secret(scope: Scope) -> list[bytes]:
    """ゲートウェイの秘密ヘッダーの値を取り出し、scope から取り除く(下流に残さない)。"""
    headers = scope.get("headers", [])
    values = [v for n, v in headers if n == _GATEWAY_HEADER]
    if values:
        scope["headers"] = [(n, v) for n, v in headers if n != _GATEWAY_HEADER]
    return values


def _gateway_secret_ok(values: list[bytes], expected: bytes) -> bool:
    # 1 つだけ・定数時間で一致(複数あれば曖昧なので拒否)
    if len(values) != 1:
        return False
    return hmac.compare_digest(values[0], expected)


async def _send_error(send: Send, status: int, error: str, challenge: str | None) -> None:
    body = json.dumps({"error": error}).encode()
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode()),
    ]
    if challenge:
        headers.append((b"www-authenticate", challenge.encode()))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class McpAuthMiddleware:
    """MCP サーバー 1 つ分の前段。トークンを検証し、方式に応じて認可してから MCP へ渡す。"""

    def __init__(
        self,
        app: ASGIApp,
        *,
        spec: McpServerSpec,
        validator: JwtValidator,
        enforcement: EnforcementMode,
        decisions: AuthDecisionLog,
        gateway_secret: str | None = None,
    ) -> None:
        if enforcement == "apim" and not gateway_secret:
            raise ValueError("apim enforcement requires a gateway secret (APIM_GATEWAY_SECRET)")
        self.app = app
        self.spec = spec
        self.validator = validator
        self.enforcement = enforcement
        self.decisions = decisions
        self._gateway_secret = gateway_secret.encode("utf-8") if gateway_secret else None

    def _record(self, decision: str, status: int, reason: str, p: Principal | None) -> None:
        self.decisions.record(
            AuthDecision(
                server=self.spec.name,
                mode=self.enforcement,
                decision=decision,
                status=status,
                reason=reason,
                oid=p.oid if p else None,
                upn=p.upn if p else None,
            )
        )

    def _authorize(self, p: Principal) -> str | None:
        """``server`` 方式の判定。拒否理由(ログ用)を返し、許可なら ``None``。"""
        if not p.is_user:
            # app-only(エージェントや中間層自身の権限)は受け付けない。委任が失敗したときの
            # 代替経路にさせないため、ロールを持っていても拒否する
            return "app-only token (no delegated user)"
        if TOOLS_API_SCOPE_NAME not in p.scopes:
            return f"scope {TOOLS_API_SCOPE_NAME} missing"
        missing = self.spec.required_roles - p.roles
        if missing:
            return f"role(s) missing: {', '.join(sorted(missing))}"
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        presented = _take_gateway_secret(scope)  # どの方式でも下流には渡さない
        if self._gateway_secret is not None and not _gateway_secret_ok(
            presented, self._gateway_secret
        ):
            # APIM を経由していない(迂回)。トークンの中身は見ずに止める
            self._record("deny", 403, GATEWAY_SECRET_MISMATCH, None)
            await _send_error(send, 403, "forbidden", None)
            return

        token = _bearer_token(scope)
        if token is None:
            self._record("deny", 401, "bearer token missing", None)
            await _send_error(send, 401, "invalid_token", _MISSING_TOKEN_CHALLENGE)
            return
        try:
            principal = await self.validator.validate(token)
        except TokenError as ex:
            # 検証器に required_scope を持たせた場合のスコープ不足は 403(RFC 6750)
            status = 403 if ex.error == "insufficient_scope" else 401
            self._record("deny", status, ex.reason, None)
            await _send_error(send, status, ex.error, ex.www_authenticate)
            return

        if self.enforcement == "server":
            reason = self._authorize(principal)
            if reason is not None:
                self._record("deny", 403, reason, principal)
                await _send_error(send, 403, "insufficient_scope", _FORBIDDEN_CHALLENGE)
                return
            self._record("allow", 200, "token, scope and roles verified by server", principal)
        else:
            # apim 方式: APIM 経由は確認済み。宛先・スコープ・ロールは APIM の判定を信頼し、
            # 署名・発行者・宛先・期限だけ再検証する
            self._record("allow", 200, "token verified by server; authorization by APIM", principal)

        state: dict[str, Any] = scope.setdefault("state", {})
        state[PRINCIPAL_STATE_KEY] = principal
        await self.app(scope, receive, send)

"""Entra ID のアクセストークン検証(MCP サーバーと中間層バックエンドで共用)。

本番と同じ経路で検証する: OpenID 設定 → JWKS(鍵 ID で公開鍵を選ぶ)→ 署名(RS256)・
発行者・宛先・期限・スコープ。HTTP クライアントは注入式で、オフラインでは
``FakeEntra.mock_transport()`` を渡す。

v2.0 トークン前提(アプリ登録の ``requestedAccessTokenVersion = 2``): ``aud`` はアプリの
クライアント ID、``iss`` は ``https://login.microsoftonline.com/<tenant>/v2.0``。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from jwt import PyJWK

AUTHORITY_HOST = "https://login.microsoftonline.com"


class TokenError(Exception):
    """トークンが無効(401 相当)。``www_authenticate`` はそのまま応答ヘッダーに使える。"""

    def __init__(self, reason: str, *, error: str = "invalid_token") -> None:
        super().__init__(reason)
        self.reason = reason
        self.error = error

    @property
    def www_authenticate(self) -> str:
        # 理由の詳細(署名 / 宛先 / 期限)は攻撃者へのヒントになるので汎用文言だけ返す
        return f'Bearer error="{self.error}", error_description="the access token is invalid"'


@dataclass(frozen=True)
class Principal:
    """検証済みトークンから取り出した呼び出し元。``is_user=False`` は app-only トークン。"""

    oid: str
    tenant_id: str
    scopes: frozenset[str]
    roles: frozenset[str]
    name: str | None
    upn: str | None
    is_user: bool
    claims: dict[str, Any]


class JwtValidator:
    """1 つの宛先(``audience``)用の検証器。JWKS は ``jwks_ttl`` 秒キャッシュする。"""

    def __init__(
        self,
        *,
        tenant_id: str,
        audience: str,
        http_client: httpx.AsyncClient,
        required_scope: str | None = None,
        authority_host: str = AUTHORITY_HOST,
        jwks_ttl: float = 3600.0,
        leeway: float = 60.0,
    ) -> None:
        self.tenant_id = tenant_id
        self.audience = audience
        self.required_scope = required_scope
        self.issuer = f"{authority_host}/{tenant_id}/v2.0"
        self._openid_url = f"{authority_host}/{tenant_id}/v2.0/.well-known/openid-configuration"
        self._http = http_client
        self._jwks_ttl = jwks_ttl
        self._leeway = leeway
        self._keys: dict[str, PyJWK] = {}
        self._fetched_at = 0.0

    async def _refresh_keys(self) -> None:
        meta = (await self._http.get(self._openid_url)).raise_for_status().json()
        jwks = (await self._http.get(meta["jwks_uri"])).raise_for_status().json()
        self._keys = {k["kid"]: PyJWK(k) for k in jwks.get("keys", []) if "kid" in k}
        self._fetched_at = time.monotonic()

    async def _key_for(self, kid: str) -> PyJWK:
        stale = time.monotonic() - self._fetched_at > self._jwks_ttl
        if stale or kid not in self._keys:
            # 鍵のローテーション直後は未知の kid が来るので 1 回だけ取り直す
            await self._refresh_keys()
        if kid not in self._keys:
            raise TokenError("unknown signing key")
        return self._keys[kid]

    async def validate(self, token: str) -> Principal:
        """署名・発行者・宛先・期限・(指定時は)スコープを検証する。失敗は ``TokenError``。"""
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as ex:
            raise TokenError(f"malformed token: {ex}") from ex
        key = await self._key_for(header.get("kid", ""))
        try:
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
                leeway=self._leeway,
                options={"require": ["exp", "iat", "aud", "iss"]},
            )
        except jwt.ExpiredSignatureError as ex:
            raise TokenError("token expired") from ex
        except jwt.PyJWTError as ex:
            raise TokenError(f"token rejected: {ex}") from ex

        scopes = frozenset((claims.get("scp") or "").split())
        roles = frozenset(claims.get("roles") or [])
        # 委任トークンには scp がある。app-only トークンは scp がなく idtyp=app(または roles のみ)
        is_user = bool(scopes) and claims.get("idtyp") != "app"
        if self.required_scope and self.required_scope not in scopes:
            raise TokenError("required scope missing", error="insufficient_scope")
        return Principal(
            oid=str(claims.get("oid", "")),
            tenant_id=str(claims.get("tid", "")),
            scopes=scopes,
            roles=roles,
            name=claims.get("name"),
            upn=claims.get("preferred_username"),
            is_user=is_user,
            claims=claims,
        )

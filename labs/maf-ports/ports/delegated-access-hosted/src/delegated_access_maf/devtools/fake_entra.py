"""オフライン用の疑似 Entra ID — トークン発行・JWKS・OBO 交換をローカルで再現する。

本物と同じ形の JWT(RS256・v2.0 形式のクレーム)を発行し、その公開鍵を JWKS として
httpx の MockTransport で配る。MCP サーバーと中間層の JWT 検証コードは、本番と同じ経路
(OpenID 設定 → JWKS → 署名・発行者・宛先・期限の検証)をそのまま通る。

使い方(テストとオフラインデモ):

    entra = FakeEntra()
    user_token = entra.issue_user_token("employee")              # aud = バックエンド API
    tools_token = entra.obo_exchange(user_token, entra.tools_scope)  # aud = ツール API
    transport = entra.mock_transport()                             # JWKS を配る httpx 用

利用者は 2 人(一般社員 / 経理担当)。ツール API のアプリロールは ``USERS`` の定義どおり。
"""

from __future__ import annotations

import base64
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from ..contracts import (
    BACKEND_API_SCOPE_NAME,
    ROLE_DOCS_FINANCE,
    ROLE_SUPPLIERS_WRITE,
    TOOLS_API_SCOPE_NAME,
)

TENANT_ID = "00000000-0000-0000-0000-00000000c0de"
BACKEND_CLIENT_ID = "11111111-1111-1111-1111-11111111bacc"
TOOLS_CLIENT_ID = "22222222-2222-2222-2222-22222222700a"
AUTHORITY_HOST = "https://login.microsoftonline.com"


@dataclass(frozen=True)
class FakeUser:
    alias: str
    oid: str
    upn: str
    name: str
    tools_roles: tuple[str, ...]


USERS: dict[str, FakeUser] = {
    "employee": FakeUser(
        alias="employee",
        oid="aaaaaaaa-0000-0000-0000-00000000e001",
        upn="employee@contoso.example",
        name="一般 社員",
        tools_roles=(),
    ),
    "finance": FakeUser(
        alias="finance",
        oid="bbbbbbbb-0000-0000-0000-00000000f001",
        upn="finance@contoso.example",
        name="経理 担当",
        tools_roles=(ROLE_SUPPLIERS_WRITE, ROLE_DOCS_FINANCE),
    ),
}


def _b64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@dataclass
class FakeEntra:
    """鍵ペアを 1 つ持つ疑似テナント。``kid`` を変えた別インスタンスは別の鍵になる。"""

    tenant_id: str = TENANT_ID
    backend_client_id: str = BACKEND_CLIENT_ID
    tools_client_id: str = TOOLS_CLIENT_ID
    kid: str = field(default_factory=lambda: uuid.uuid4().hex[:16])

    def __post_init__(self) -> None:
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # --- 発行者のメタデータ ------------------------------------------------------------

    @property
    def issuer(self) -> str:
        return f"{AUTHORITY_HOST}/{self.tenant_id}/v2.0"

    @property
    def openid_config_url(self) -> str:
        return f"{AUTHORITY_HOST}/{self.tenant_id}/v2.0/.well-known/openid-configuration"

    @property
    def jwks_uri(self) -> str:
        return f"{AUTHORITY_HOST}/{self.tenant_id}/discovery/v2.0/keys"

    @property
    def backend_scope(self) -> str:
        return f"api://{self.backend_client_id}/{BACKEND_API_SCOPE_NAME}"

    @property
    def tools_scope(self) -> str:
        return f"api://{self.tools_client_id}/{TOOLS_API_SCOPE_NAME}"

    def jwks(self) -> dict[str, Any]:
        pub = self._key.public_key().public_numbers()
        return {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "kid": self.kid,
                    "alg": "RS256",
                    "n": _b64url_uint(pub.n),
                    "e": _b64url_uint(pub.e),
                }
            ]
        }

    def openid_config(self) -> dict[str, Any]:
        return {"issuer": self.issuer, "jwks_uri": self.jwks_uri}

    def mock_transport(self) -> httpx.MockTransport:
        """OpenID 設定と JWKS だけを返す httpx のトランスポート(それ以外は 404)。"""

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if url == self.openid_config_url:
                return httpx.Response(200, json=self.openid_config())
            if url == self.jwks_uri:
                return httpx.Response(200, json=self.jwks())
            return httpx.Response(404, json={"error": "not_found", "url": url})

        return httpx.MockTransport(handler)

    # --- トークン発行 ------------------------------------------------------------------

    def _sign(self, claims: dict[str, Any]) -> str:
        return jwt.encode(claims, self._key, algorithm="RS256", headers={"kid": self.kid})

    def issue_user_token(
        self,
        alias: str,
        *,
        lifetime: int = 3600,
        now: float | None = None,
    ) -> str:
        """利用者が CLI でサインインして得るトークン(aud = バックエンド API、scp = access_as_user)。"""
        user = USERS[alias]
        t = int(now if now is not None else time.time())
        return self._sign(
            {
                "aud": self.backend_client_id,
                "iss": self.issuer,
                "iat": t,
                "nbf": t,
                "exp": t + lifetime,
                "tid": self.tenant_id,
                "oid": user.oid,
                "sub": f"sub-{user.alias}",
                "preferred_username": user.upn,
                "name": user.name,
                "scp": BACKEND_API_SCOPE_NAME,
                "azp": self.backend_client_id,
                "ver": "2.0",
            }
        )

    def obo_exchange(
        self,
        user_assertion: str,
        scope: str,
        *,
        lifetime: int = 3600,
        now: float | None = None,
        require_mfa: bool = False,
    ) -> dict[str, Any]:
        """OBO 交換(MSAL の acquire_token_on_behalf_of と同じ形の dict を返す)。

        - 入力トークンの署名・宛先を検証し、利用者(oid)を変えずに宛先だけをツール API に変える
        - ツール API のアプリロールは利用者の割り当て(``USERS``)から ``roles`` に入れる
        - ``require_mfa=True`` は条件付きアクセスが追加の認証を要求した状態を再現し、
          claims challenge 付きの ``interaction_required`` を返す(本物の MSAL と同じキー)
        """
        claims = jwt.decode(
            user_assertion,
            self._key.public_key(),
            algorithms=["RS256"],
            audience=self.backend_client_id,
            issuer=self.issuer,
        )
        if require_mfa:
            challenge = json.dumps({"access_token": {"acrs": {"essential": True, "value": "c1"}}})
            return {
                "error": "interaction_required",
                "error_description": "AADSTS50076: multi-factor authentication required (fake)",
                "suberror": "basic_action",
                "claims": challenge,
            }
        if scope != self.tools_scope:
            return {"error": "invalid_scope", "error_description": f"unknown scope {scope}"}
        user = next(u for u in USERS.values() if u.oid == claims["oid"])
        t = int(now if now is not None else time.time())
        token_claims: dict[str, Any] = {
            "aud": self.tools_client_id,
            "iss": self.issuer,
            "iat": t,
            "nbf": t,
            "exp": t + lifetime,
            "tid": self.tenant_id,
            "oid": user.oid,
            "sub": f"sub-{user.alias}-tools",
            "preferred_username": user.upn,
            "name": user.name,
            "scp": TOOLS_API_SCOPE_NAME,
            "azp": self.backend_client_id,
            "ver": "2.0",
        }
        if user.tools_roles:
            token_claims["roles"] = list(user.tools_roles)
        return {
            "access_token": self._sign(token_claims),
            "token_type": "Bearer",
            "expires_in": lifetime,
        }

    def issue_app_only_token(self, audience: str, *, roles: tuple[str, ...] = ()) -> str:
        """app-only(利用者なし)のトークン。OBO の代わりにこれが使われていないことの検証用。"""
        t = int(time.time())
        claims: dict[str, Any] = {
            "aud": audience,
            "iss": self.issuer,
            "iat": t,
            "nbf": t,
            "exp": t + 3600,
            "tid": self.tenant_id,
            "oid": "cccccccc-0000-0000-0000-0000000a9901",
            "sub": "app-only",
            "idtyp": "app",
            "azp": self.backend_client_id,
            "ver": "2.0",
        }
        if roles:
            claims["roles"] = list(roles)
        return self._sign(claims)

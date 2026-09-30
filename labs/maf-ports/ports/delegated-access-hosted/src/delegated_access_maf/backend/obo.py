"""OBO 交換と Foundry 用トークン(中間層 = 機密クライアント)。

2 種類のトークンを別々に取る(公式手順の「3 つのトークンは互換ではない」):

- **OBO**: 利用者トークン(aud = バックエンド API)を assertion にして、ツール API 宛ての
  委任トークンを得る。利用者は変わらず、宛先だけが変わる。MSAL の
  ``acquire_token_on_behalf_of``
- **Foundry 用**: バックエンド自身のワークロードトークン(``https://ai.azure.com/.default``)。
  hosted agent を呼ぶ権限の証明で、利用者の権限は表さない。MSAL の
  ``acquire_token_for_client``(同じ機密クライアントを使う)

OBO が失敗したら**アプリ権限に切り替えない**。条件付きアクセスなどで追加の操作が必要なら
MSAL は ``claims`` 付きのエラーを返すので、そのまま利用者(CLI)へ返して取り直してもらう。

どちらも MSAL の同期 API をスレッドで回す。MSAL はトークンをメモリにキャッシュする
(OBO は assertion ごと、Foundry 用はアプリごと)ので、毎リクエストの交換は通信にならない。
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    import msal

    from ..devtools.fake_entra import FakeEntra
    from .settings import BackendSettings

#: 利用者の再認証で解消する MSAL のエラー(assertion の期限切れ・同意不足・MFA 要求など)
_REAUTH_ERRORS = frozenset(
    {"interaction_required", "invalid_grant", "consent_required", "login_required"}
)


class OboChallenge(Exception):
    """条件付きアクセスなどが追加の認証を要求した(``claims`` チャレンジ付き)。"""

    def __init__(self, claims: str, *, error: str, description: str = "") -> None:
        super().__init__(error)
        self.claims = claims
        self.error = error
        self.description = description

    @property
    def claims_b64(self) -> str:
        """``WWW-Authenticate`` の ``claims=`` に入れる値(claims の JSON を base64)。"""
        return base64.b64encode(self.claims.encode()).decode()


class OboError(Exception):
    """OBO が失敗した。``reauth=True`` は利用者の再サインインで解消する種類。"""

    def __init__(self, error: str, description: str = "", *, reauth: bool) -> None:
        super().__init__(error)
        self.error = error
        self.description = description
        self.reauth = reauth


def token_from_msal_result(result: dict[str, Any] | None) -> str:
    """MSAL 形式の結果からアクセストークンを取り出す。失敗は ``OboChallenge`` / ``OboError``。

    エラーの説明文(``error_description``)はログに残すだけで利用者には返さない想定。
    """
    if not result:
        raise OboError("no_result", reauth=False)
    token = result.get("access_token")
    if token:
        return str(token)
    error = str(result.get("error") or "unknown_error")
    description = str(result.get("error_description") or "")
    claims = result.get("claims")
    if claims:
        raise OboChallenge(str(claims), error=error, description=description)
    suberror = str(result.get("suberror") or "")
    raise OboError(error, description, reauth=error in _REAUTH_ERRORS or suberror in _REAUTH_ERRORS)


class OboExchanger(Protocol):
    async def exchange(self, user_assertion: str) -> str:
        """利用者トークンをツール API 宛ての委任トークンに交換する。"""
        ...


class FoundryTokenProvider(Protocol):
    async def get_token(self) -> str:
        """hosted agent を呼ぶためのバックエンド自身のトークン。"""
        ...


class MsalOboExchanger:
    def __init__(self, app: msal.ConfidentialClientApplication, scope: str) -> None:
        self._app = app
        self._scope = scope

    async def exchange(self, user_assertion: str) -> str:
        result = await asyncio.to_thread(
            self._app.acquire_token_on_behalf_of, user_assertion, [self._scope]
        )
        return token_from_msal_result(result)


class MsalFoundryTokenProvider:
    def __init__(self, app: msal.ConfidentialClientApplication, scope: str) -> None:
        self._app = app
        self._scope = scope

    async def get_token(self) -> str:
        result = await asyncio.to_thread(self._app.acquire_token_for_client, [self._scope])
        return token_from_msal_result(result)


def build_msal_app(settings: BackendSettings) -> msal.ConfidentialClientApplication:
    """バックエンドの機密クライアント(OBO と Foundry 用トークンで共用)。"""
    import msal

    if not settings.backend_client_secret:
        raise ValueError("BACKEND_CLIENT_SECRET が未設定です(OBO には機密クライアントが必要)")
    return msal.ConfidentialClientApplication(
        settings.backend_api_client_id,
        authority=settings.authority,
        client_credential=settings.backend_client_secret,
    )


# --- オフライン用 ----------------------------------------------------------------------


class FakeEntraOboExchanger:
    """``FakeEntra.obo_exchange`` を使う OBO(テスト・オフラインデモ用)。

    ``require_mfa`` を True(または True を返す関数)にすると、条件付きアクセスの
    claims チャレンジを再現する。
    """

    def __init__(
        self,
        entra: FakeEntra,
        *,
        scope: str | None = None,
        require_mfa: bool | Callable[[], bool] = False,
    ) -> None:
        self._entra = entra
        self._scope = scope or entra.tools_scope
        self._require_mfa = require_mfa
        self.calls = 0

    async def exchange(self, user_assertion: str) -> str:
        self.calls += 1
        mfa = self._require_mfa() if callable(self._require_mfa) else self._require_mfa
        return token_from_msal_result(
            self._entra.obo_exchange(user_assertion, self._scope, require_mfa=mfa)
        )


class StaticFoundryToken:
    """決まった値を返す Foundry 用トークン(テスト用)。"""

    def __init__(self, token: str = "foundry-workload-token-for-tests") -> None:
        self.token = token
        self.calls = 0

    async def get_token(self) -> str:
        self.calls += 1
        return self.token

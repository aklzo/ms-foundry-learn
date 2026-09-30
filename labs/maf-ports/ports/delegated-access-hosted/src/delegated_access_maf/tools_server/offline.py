"""ツールサーバーをプロセス内で動かすオフライン用ハーネス(テスト・エージェント側の結合確認用)。

    async with offline_tools_server(entra, enforcement="apim") as tools:
        async with tools.client(token) as http:          # Authorization: Bearer <token> 付き
            r = await http.post("/docs/mcp", json=...)   # base_url は tools.base_url

- ``enforcement="server"``: ツールサーバー単体(方式 B)
- ``enforcement="apim"``: ``ApimEmulator``(infra/apim/policies/*.xml)→ ツールサーバー(方式 A)。
  ゲートウェイの秘密はハーネスごとに乱数で作り、エミュレーターの Named Value とサーバーの設定に渡す
  (``tools.gateway_secret``。迂回のテストで使う)
- JWKS は ``FakeEntra.mock_transport()`` から取る(ネットワークなし)
- 取引先マスタと文書は同梱データ(``data/``)。差し替える場合は ``docs`` / ``suppliers`` を渡す

MAF の ``MCPStreamableHTTPTool`` などに渡すときは ``tools.transport``(httpx の ASGI
トランスポート)で ``httpx.AsyncClient`` を作り、MCP の URL は ``tools.base_url + spec.path``。
"""

from __future__ import annotations

import contextlib
import secrets
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx
from starlette.applications import Starlette
from starlette.types import ASGIApp

from ..contracts import EnforcementMode
from ..devtools.fake_entra import FakeEntra
from .apim_emulator import ApimEmulator, named_values_for
from .app import create_app, make_validator
from .docs_search import DocsSearch, InMemoryDocs
from .settings import DEFAULT_DOCS_DIR, DEFAULT_SUPPLIERS_DATA, ToolsServerSettings
from .suppliers import SupplierStore

#: ASGI トランスポートはスキームを見ない。エージェント側の設定は https(ループバック以外)しか受け付けない
OFFLINE_BASE_URL = "https://tools.offline"


@dataclass
class OfflineToolsServer:
    app: ASGIApp  # クライアントが呼ぶ入口(apim 方式ならエミュレーター)
    server: Starlette  # ツールサーバー本体(app.state に判定記録など)
    gateway: ApimEmulator | None
    suppliers: SupplierStore
    docs: DocsSearch
    enforcement: EnforcementMode
    gateway_secret: str | None = field(default=None, repr=False)
    base_url: str = OFFLINE_BASE_URL

    @property
    def transport(self) -> httpx.ASGITransport:
        return httpx.ASGITransport(app=self.app)

    def client(self, token: str | None = None, **kwargs: object) -> httpx.AsyncClient:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return httpx.AsyncClient(
            transport=self.transport,
            base_url=self.base_url,
            headers=headers,
            **kwargs,  # type: ignore[arg-type]
        )


@contextlib.asynccontextmanager
async def offline_tools_server(
    entra: FakeEntra,
    *,
    enforcement: EnforcementMode = "server",
    docs: DocsSearch | None = None,
    suppliers: SupplierStore | None = None,
) -> AsyncIterator[OfflineToolsServer]:
    gateway_secret = secrets.token_urlsafe(32) if enforcement == "apim" else None
    settings = ToolsServerSettings(
        tenant_id=entra.tenant_id,
        tools_client_id=entra.tools_client_id,
        enforcement_mode=enforcement,
        apim_gateway_secret=gateway_secret,
    )
    docs = docs if docs is not None else InMemoryDocs.from_dir(DEFAULT_DOCS_DIR)
    suppliers = (
        suppliers if suppliers is not None else SupplierStore.from_json(DEFAULT_SUPPLIERS_DATA)
    )
    async with httpx.AsyncClient(transport=entra.mock_transport()) as jwks_http:
        server = create_app(
            settings,
            validator=make_validator(settings, http_client=jwks_http),
            docs=docs,
            suppliers=suppliers,
        )
        gateway = None
        if gateway_secret is not None:
            gateway = ApimEmulator(
                server,
                named_values=named_values_for(
                    entra.tenant_id, entra.tools_client_id, gateway_secret
                ),
                http_client=jwks_http,
            )
        async with server.router.lifespan_context(server):
            yield OfflineToolsServer(
                app=gateway or server,
                server=server,
                gateway=gateway,
                suppliers=suppliers,
                docs=docs,
                enforcement=enforcement,
                gateway_secret=gateway_secret,
            )

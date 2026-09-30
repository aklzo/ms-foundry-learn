"""MCP ツールサーバー — 3 つの FastMCP サーバーを契約どおりのパスに mount した 1 つの ASGI アプリ。

    /docs/mcp            search_documents            認証済みの全社員(文書は権限で絞り込み)
    /suppliers/mcp       list_suppliers, get_supplier 認証済みの全社員
    /supplier-admin/mcp  update_payment_terms         Suppliers.Write ロールのみ
    /healthz             ヘルスチェック(認証なし。Container Apps のプローブ用)

MCP のトランスポートは **ステートレスな Streamable HTTP + JSON 応答**(SSE なし)。
理由: (1) APIM を前段に置いても応答のバッファリングやストリーム切断の問題が起きない
(2) セッション ID を持たないので、利用者 A のトークンで開いたセッションを利用者 B の
リクエストが再利用する経路が構造的にない(毎リクエストでトークンを検証する)
(3) GET(サーバー発のストリーム)も DELETE(セッション終了)も使わないので、APIM の
オペレーションは POST /mcp だけで足りる。

エンドポイントごとの前段 ``McpAuthMiddleware`` が方式(``server`` / ``apim``)に応じて判定し
(``apim`` では APIM が付けるゲートウェイの秘密ヘッダーも必須)、
検証済みの ``Principal`` をツール関数に渡す(``auth.principal_from``)。
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from ..contracts import (
    DOCS,
    MCP_SERVERS,
    SUPPLIER_ADMIN,
    SUPPLIERS,
    TOOLS_API_SCOPE_NAME,
    EnforcementMode,
    McpServerSpec,
)
from ..jwt_validation import JwtValidator
from .auth import AuthDecisionLog, McpAuthMiddleware, principal_from
from .docs_search import DocsSearch
from .settings import ToolsServerSettings
from .suppliers import InvalidUpdateError, SupplierNotFoundError, SupplierStore

HEALTH_PATH = "/healthz"


def make_validator(
    settings: ToolsServerSettings,
    *,
    http_client: httpx.AsyncClient,
    enforcement: EnforcementMode | None = None,
) -> JwtValidator:
    """方式に合わせた検証器。``server`` はスコープも検証器で見る、``apim`` は署名・宛先・期限だけ。"""
    mode = enforcement or settings.enforcement_mode
    return JwtValidator(
        tenant_id=settings.tenant_id,
        audience=settings.tools_client_id,
        http_client=http_client,
        required_scope=TOOLS_API_SCOPE_NAME if mode == "server" else None,
    )


def _split_path(spec: McpServerSpec) -> tuple[str, str]:
    """``/docs/mcp`` → (``/docs``, ``/mcp``)。mount 先と FastMCP 側のパスに分ける。"""
    prefix, _, endpoint = spec.path.rpartition("/")
    return prefix, "/" + endpoint


def _new_server(spec: McpServerSpec) -> FastMCP:
    _, endpoint = _split_path(spec)
    return FastMCP(
        name=f"dah-{spec.name}",
        instructions=spec.description,
        streamable_http_path=endpoint,
        stateless_http=True,
        json_response=True,
        # FastMCP は host=127.0.0.1 のとき DNS リバインディング対策(Host ヘッダーの許可リスト)を
        # 自動で有効にし、APIM / Container Apps 経由の Host を 421 で落とす。対策の対象は
        # 認証なしのローカルサーバーで、ここは全リクエストに Bearer トークンを要求するので無効にする
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        log_level="WARNING",
    )


def _build_docs_server(docs: DocsSearch) -> FastMCP:
    server = _new_server(DOCS)

    @server.tool(
        name="search_documents",
        description=(
            "社内文書(規程・手順書)を全文検索する。サインインしている利用者が閲覧できる文書だけが"
            "返る。query は日本語のキーワードや質問文、top は返す件数(1〜10)。"
        ),
    )
    async def search_documents(query: str, ctx: Context, top: int = 3) -> dict[str, Any]:
        principal = principal_from(ctx)
        hits = await docs.search(query, principal=principal, top=top)
        # 絞り込みで除外した件数は返さない(見えない文書の存在自体を漏らさない)
        return {"query": query, "results": [h.to_dict() for h in hits]}

    return server


def _build_suppliers_server(store: SupplierStore) -> FastMCP:
    server = _new_server(SUPPLIERS)

    @server.tool(
        name="list_suppliers",
        description="取引先マスタの一覧(取引先 ID・名称・区分・支払サイト)を返す。",
    )
    async def list_suppliers(ctx: Context) -> dict[str, Any]:
        principal_from(ctx)  # 検証済みの呼び出し元がいることだけ確認(参照は全社員に許可)
        return {"suppliers": [s.to_summary() for s in store.all_suppliers()]}

    @server.tool(
        name="get_supplier",
        description="取引先 ID(例: S-1001)を指定して取引先マスタの詳細を返す。",
    )
    async def get_supplier(supplier_id: str, ctx: Context) -> dict[str, Any]:
        principal_from(ctx)
        try:
            return store.get(supplier_id).to_dict()
        except SupplierNotFoundError as ex:
            raise ToolError(str(ex)) from ex

    return server


def _build_supplier_admin_server(store: SupplierStore) -> FastMCP:
    server = _new_server(SUPPLIER_ADMIN)

    @server.tool(
        name="update_payment_terms",
        description=(
            "取引先の支払サイト(日数)を更新する。Suppliers.Write ロールの利用者だけが使える。"
            "更新は監査記録に残る。"
        ),
    )
    async def update_payment_terms(supplier_id: str, days: int, ctx: Context) -> dict[str, Any]:
        principal = principal_from(ctx)
        try:
            updated, record = await store.update_payment_terms(
                supplier_id, days, principal=principal
            )
        except (SupplierNotFoundError, InvalidUpdateError) as ex:
            raise ToolError(str(ex)) from ex
        return {
            "supplier_id": updated.supplier_id,
            "name": updated.name,
            "payment_terms_days": {"before": record.before, "after": record.after},
            "updated_by": record.upn or record.oid,
            "updated_at": record.at,
        }

    return server


def create_app(
    settings: ToolsServerSettings,
    *,
    validator: JwtValidator,
    docs: DocsSearch,
    suppliers: SupplierStore,
    enforcement: EnforcementMode | None = None,
) -> Starlette:
    """ツールサーバーの ASGI アプリ。``enforcement`` を省略すると ``settings`` の方式を使う。

    ``app.state`` に ``auth_decisions``(認可判定の記録)・``suppliers``・``docs``・
    ``enforcement``・``validator`` を置く(テストと運用時の確認用)。
    """
    mode: EnforcementMode = enforcement or settings.enforcement_mode
    settings.require_gateway_secret(mode)  # apim 方式で秘密がなければ起動しない
    decisions = AuthDecisionLog()
    servers: dict[str, FastMCP] = {
        DOCS.name: _build_docs_server(docs),
        SUPPLIERS.name: _build_suppliers_server(suppliers),
        SUPPLIER_ADMIN.name: _build_supplier_admin_server(suppliers),
    }

    routes: list[Route | Mount] = []
    for spec in MCP_SERVERS:
        prefix, _ = _split_path(spec)
        guarded = McpAuthMiddleware(
            servers[spec.name].streamable_http_app(),
            spec=spec,
            validator=validator,
            enforcement=mode,
            decisions=decisions,
            gateway_secret=settings.apim_gateway_secret if mode == "apim" else None,
        )
        routes.append(Mount(prefix, app=guarded))

    async def health(_: Request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "enforcement_mode": mode,
                "mcp_servers": {s.name: s.path for s in MCP_SERVERS},
            }
        )

    routes.insert(0, Route(HEALTH_PATH, health, methods=["GET"]))

    @contextlib.asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        # mount した FastMCP はそれぞれのセッションマネージャーを親アプリの lifespan で起動する
        async with contextlib.AsyncExitStack() as stack:
            for server in servers.values():
                await stack.enter_async_context(server.session_manager.run())
            yield

    app = Starlette(routes=routes, lifespan=lifespan)
    app.state.auth_decisions = decisions
    app.state.suppliers = suppliers
    app.state.docs = docs
    app.state.enforcement = mode
    app.state.settings = settings
    app.state.validator = validator
    return app


def describe(app: Starlette) -> str:
    """起動ログ用の 1 行(トークンや鍵は含まない)。"""
    return json.dumps(
        {
            "enforcement_mode": app.state.enforcement,
            "mcp_servers": [s.path for s in MCP_SERVERS],
            "health": HEALTH_PATH,
        },
        ensure_ascii=False,
    )

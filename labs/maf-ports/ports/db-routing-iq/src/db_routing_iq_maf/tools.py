"""エージェントの 2 ツール — knowledge base MCP と Web fallback — の組み立て。

1. **knowledge base MCP ツール**: AI Search の knowledge base はそれ自体が
   MCP サーバーで、``{search-endpoint}/knowledgebases/{kb}/mcp?api-version=...``
   に公開ツール ``knowledge_base_retrieve`` を 1 つだけ持つ。認証は
   ``Authorization: Bearer``(Search Index Data Reader ロール)または
   ``api-key``(管理キー)ヘッダー。ラボはキー認証で統一する。

   ヘッダーの渡し方(2026-09-29 に agent-framework-core 1.19.0 の _mcp.py で
   再確認 — Port 6 github-mcp と同じ結論):

   - **``static_headers``(1.19.0 で追加。1.18.0 には無い)を使う。** 固定
     ヘッダーを構築時にコピーし、接続中の全リクエスト(initialize /
     tools/list / ping / tools/call)に付ける。注入は設定した URL と同一
     オリジンのリクエストに限られ、別オリジンへのリダイレクトでは外される
     — キー漏出防止をフレームワークが肩代わりする
   - 旧実装(2026-07-31 ライブ検証時)は ``httpx.AsyncClient(headers=...)`` を
     ``http_client`` に渡していた(Port 6 が精読した 1.12.1 の
     ``header_provider`` は call_tool 時にしか付かず、接続段階で認証が通らな
     かったため)。自前クライアントのヘッダーはオリジン制限が利用者責務
     (_mcp.py の docstring)なので、フレームワーク側の仕組みに寄せた
   - HTTP クライアントは MCP ツールが自前で生成・破棄する(タイムアウト 30 秒 /
     SSE 読み取り 300 秒)。接続・切断は ``async with agent:`` が担う。
     ``http_client`` 引数はオフラインテストの MockTransport 注入用に残す

2. **Web fallback ツール**: 元アプリ第三段の DuckDuckGo 検索。knowledge base
   の web knowledge source(Bing・プレビュー・別課金・Azure 境界外への
   データフロー)は使わず、自前 DDG の関数ツールにする(設計判断は README)。
   MAF の ``Agent(tools=[...])`` は素の callable からツールスキーマを推論
   するので、httpx クライアントをクロージャで束縛して返す。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from .config import DbRoutingIqSettings
from .search import ddg_search

#: エージェントから見た MCP ツール群の論理名
KB_TOOL_NAME = "knowledge_base"

#: knowledge base が公開する唯一の MCP ツール。allow-list で明示して、
#: サービス側が将来ツールを増やしても公開面が広がらないようにする
KB_RETRIEVE_TOOL = "knowledge_base_retrieve"

#: 元アプリの DuckDuckGoSearchRun(num_results=5)と同値
WEB_SEARCH_MAX_RESULTS = 5


def build_kb_headers(settings: DbRoutingIqSettings) -> dict[str, str]:
    """MCP エンドポイントへ送る全リクエスト共通ヘッダー(純関数)。

    管理キーの ``api-key`` ヘッダー(開発用途向けの公式サポート経路)。
    本番は Bearer トークン+Search Index Data Reader が推奨(README)。
    """
    return {"api-key": settings.search_api_key}


def build_kb_mcp_tool(
    settings: DbRoutingIqSettings,
    *,
    http_client: Any | None = None,
    tool_cls: type | None = None,
) -> Any:
    """knowledge base の MCP エンドポイントを指す MAF MCP ツールを組み立てる。

    api-key は ``static_headers`` で渡す(同一オリジン限定の注入はフレーム
    ワークが保証)。``http_client`` は通常 None(MAF が生成・破棄)で、
    オフラインテストが MockTransport 付きクライアントを差し込むためのシーム。
    ``tool_cls`` もテスト用の注入シーム(既定は MAF の MCPStreamableHTTPTool)。
    接続はここでは行わない — ``async with agent:``(または run)がツールを
    enter した時点で initialize / tools/list が走り、knowledge_base_retrieve が
    ``tool.functions`` に展開される。
    """
    if tool_cls is None:
        from agent_framework import MCPStreamableHTTPTool as tool_cls  # type: ignore[no-redef]

    return tool_cls(
        KB_TOOL_NAME,
        settings.kb_mcp_url,
        description=(
            "Foundry IQ knowledge base over product / support / finance sources "
            "(agentic retrieval via Azure AI Search)"
        ),
        static_headers=build_kb_headers(settings),
        http_client=http_client,
        allowed_tools=[KB_RETRIEVE_TOOL],
        load_prompts=False,  # 公開面はツールのみ(github-mcp と同じ方針)
    )


def make_web_search_tool(http: Any) -> Callable[..., Awaitable[str]]:
    """Web fallback の関数ツール(元アプリの web_research ツール相当)。

    元実装は検索失敗を例外にせず文字列で返していた(LangGraph ReAct が
    続行できるように)。同じ流儀で SearchError も文字列にする。
    """

    async def web_search(query: str) -> str:
        """Search the public web. Use ONLY when the knowledge base returned
        nothing relevant to the user's question.

        Args:
            query: Search query, e.g. "latest smartphone market trends".
        """
        try:
            hits = await ddg_search(http, query, WEB_SEARCH_MAX_RESULTS)
        except Exception as exc:  # noqa: BLE001 - 元実装は全例外を文字列化していた
            return f"Search failed: {exc}. Providing answer based on general knowledge."
        if not hits:
            return "(no results)"
        return "\n".join(f"- **{hit.title}**\n  {hit.url}\n  {hit.snippet}" for hit in hits)

    return web_search

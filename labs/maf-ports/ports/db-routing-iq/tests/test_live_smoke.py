"""ライブスモーク(実 Foundry + 実 AI Search knowledge base)。既定では除外
され、``uv run pytest -m live`` で実行する。要 labs/maf-ports/.env
(AZURE_SEARCH_* は ports/db-routing-iq/infra/main.bicep の出力)。

**前提: knowledge base が存在すること。** 事前に 1 回だけ実行しておく:

    uv run python scripts/setup_kb.py

確認項目(PORTING.md §4 + 本ポートの核心):
1. MCP 接続(initialize / tools/list が api-key ヘッダー付きで通り、
   knowledge_base_retrieve が functions に展開される)
2. **3 ドメイン各 1 問**: サービス側ルーティング(agentic retrieval)が
   正しいソースへ振り分け、そのソースにしか無いファクトで回答すること
3. **ドメイン外 1 問**: KB が空振りし、web_search フォールバックに入ること
4. トレースが App Insights に届くこと(このテストでは送信の有効化まで。
   到達確認は CLI 実行後に az monitor app-insights query で行う)
"""

import pytest

from db_routing_iq_maf.config import ConfigError, DbRoutingIqSettings

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def settings() -> DbRoutingIqSettings:
    try:
        return DbRoutingIqSettings.from_env()
    except ConfigError as exc:
        pytest.skip(f"live 設定なし: {exc}")


async def ask(settings: DbRoutingIqSettings, question: str) -> tuple[str, list[str]]:
    from db_routing_iq_maf.agents import build_chat_client, build_routing_agent
    from db_routing_iq_maf.observability import setup_tracing
    from db_routing_iq_maf.query import response_text, run_query, summarize_tool_calls
    from db_routing_iq_maf.search import default_http_client
    from db_routing_iq_maf.tools import build_kb_mcp_tool, make_http_client, make_web_search_tool

    setup_tracing(settings.app_insights_connection_string)

    kb_http = make_http_client(settings)
    web_http = default_http_client()
    try:
        kb_tool = build_kb_mcp_tool(settings, kb_http)
        agent = build_routing_agent(
            build_chat_client(settings), kb_tool, make_web_search_tool(web_http)
        )
        async with agent:
            # 接続確認: api-key ヘッダー付きで initialize / tools/list が通り、
            # allow-list 後も knowledge_base_retrieve が展開されている
            assert kb_tool.is_connected
            names = [f.name for f in kb_tool.functions]
            assert "knowledge_base_retrieve" in names, f"KB の MCP ツールが未展開: {names}"

            response = await run_query(agent, question)
    finally:
        await web_http.aclose()
        await kb_http.aclose()

    return response_text(response), summarize_tool_calls(response)


@pytest.mark.parametrize(
    ("question", "answer_fragment", "domain"),
    [
        # 各ファクトは期待ドメインのコーパスにしか無い(test_query.py で固定済み)
        ("Aurora X10 の本体重量と、バッテリーでの連続投影時間を教えてください", "1.2", "products"),
        ("商品が届いてから何日以内なら返品を申請できますか?", "30", "support"),
        ("FY2025 の売上高はいくらで、前年比何%の成長でしたか?", "84", "finance"),
    ],
    ids=["products", "support", "finance"],
)
async def test_in_domain_question_grounds_on_expected_source(
    settings: DbRoutingIqSettings, question: str, answer_fragment: str, domain: str
) -> None:
    answer, tool_calls = await ask(settings, question)

    assert answer.strip(), "空応答"
    assert "knowledge_base_retrieve" in tool_calls, (
        f"KB が呼ばれていない(tool_calls={tool_calls})"
    )
    assert answer_fragment in answer, (
        f"{domain} ソースのファクト {answer_fragment!r} が回答に無い: {answer[:300]}"
    )


async def test_out_of_domain_question_falls_back_to_web(
    settings: DbRoutingIqSettings,
) -> None:
    """元アプリの第三段(DDG fallback)に対応する経路。KB では答えられない
    鮮度依存の質問で web_search が呼ばれる(または Web 由来と明示される)。"""
    answer, tool_calls = await ask(settings, "2026 年現在の日本の首相は誰ですか?")

    assert answer.strip(), "空応答"
    assert "web_search" in tool_calls or "Web Search Result" in answer, (
        f"Web fallback に入っていない(tool_calls={tool_calls}): {answer[:300]}"
    )

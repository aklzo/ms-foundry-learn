"""ライブスモーク(実 GitHub リモート MCP サーバー + 実モデル)。既定では
除外され、``uv run pytest -m live`` で実行する。要 labs/maf-ports/.env
(Foundry 設定)+ ``GITHUB_TOKEN``(PAT。`gh auth token` でも取得可)。

確認項目(PORTING.md §4):
1. リモート MCP サーバーへの接続(initialize / tools/list が PAT ヘッダー付きで
   通り、ツール群が functions に展開される)
2. 実モデルがツールを呼んで公開リポジトリ(microsoft/agent-framework)への
   読み取り質問に回答すること
3. トレースが App Insights に届くこと(このテストでは送信の有効化まで。
   到達確認は CLI 実行後に az monitor app-insights query で行う)
"""

import pytest

from github_mcp_maf.config import ConfigError, GithubMcpSettings

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def settings() -> GithubMcpSettings:
    try:
        return GithubMcpSettings.from_env()
    except ConfigError as exc:
        pytest.skip(f"live 設定なし: {exc}")


async def test_remote_mcp_query_live(settings: GithubMcpSettings) -> None:
    from github_mcp_maf.agents import build_chat_client, build_github_agent
    from github_mcp_maf.observability import setup_tracing
    from github_mcp_maf.query import build_full_query, run_query
    from github_mcp_maf.tools import build_github_mcp_tool, make_http_client

    setup_tracing(settings.app_insights_connection_string)

    http = make_http_client(settings)
    try:
        tool = build_github_mcp_tool(settings, http)
        agent = build_github_agent(build_chat_client(settings), tool)
        question = build_full_query(
            "Summarize the most recently merged pull requests (titles and links).",
            "microsoft/agent-framework",
        )
        async with agent:
            # 接続確認: PAT ヘッダー付きで initialize / tools/list が通っている
            assert tool.is_connected
            assert tool.functions, "リモート MCP のツールが 1 つも展開されていない"

            answer = await run_query(agent, question)
    finally:
        await http.aclose()

    assert answer.strip()
    assert len(answer) > 20

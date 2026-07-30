"""CLI エントリポイント(元アプリの Streamlit UI の置き換え)。

    uv run github-mcp-maf "microsoft/agent-framework の最近の PR 動向は?"
    uv run github-mcp-maf --repo microsoft/agent-framework "Find issues labeled as bugs"
    uv run github-mcp-maf --timeout 180 "..."

前提: 環境変数 GITHUB_TOKEN(PAT。`gh auth token` でも取得可)と共有基盤の
Foundry 設定(labs/maf-ports/.env)。Docker は不要 — 接続先は GitHub 公式
リモート MCP サーバー(既定 https://api.githubcopilot.com/mcp/)。

``async with agent:`` が MCP 接続のライフサイクルを担う(enter で initialize +
tools/list、exit で切断)。PAT ヘッダー付き httpx クライアントの後始末は
こちら(finally)の責務。
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from .agents import build_chat_client, build_github_agent
from .config import ConfigError, GithubMcpSettings
from .observability import setup_tracing
from .query import DEFAULT_TIMEOUT_SECONDS, build_full_query, run_query
from .tools import build_github_mcp_tool, make_http_client


def main() -> None:
    parser = argparse.ArgumentParser(
        description="GitHub リポジトリの自然言語照会(MAF + GitHub リモート MCP 移植版)"
    )
    parser.add_argument(
        "question",
        help="質問(例: 'Show me recent merged PRs in microsoft/agent-framework')",
    )
    parser.add_argument(
        "--repo",
        help="owner/repo 形式のリポジトリ指定。質問文に含まれていなければ 'in <repo>' を連結"
        "(元アプリの Repository 入力欄)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"全体タイムアウト秒(既定 {DEFAULT_TIMEOUT_SECONDS:.0f} — 元アプリと同値)",
    )
    args = parser.parse_args()
    try:
        asyncio.run(_run(args))
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)


async def _run(args: argparse.Namespace) -> None:
    settings = GithubMcpSettings.from_env()
    if setup_tracing(settings.app_insights_connection_string):
        print("tracing: App Insights 有効", file=sys.stderr)

    print(
        f"[mcp] {settings.mcp_url} "
        f"(toolsets={settings.toolsets or 'all'}, readonly={'on' if settings.readonly else 'off'})",
        file=sys.stderr,
    )

    http = make_http_client(settings)
    try:
        tool = build_github_mcp_tool(settings, http)
        agent = build_github_agent(build_chat_client(settings), tool)
        full_query = build_full_query(args.question, args.repo)
        try:
            async with agent:  # enter で MCP 接続、exit で切断
                answer = await run_query(agent, full_query, timeout=args.timeout)
        except TimeoutError:
            # 元アプリの "Error: Request timed out after 120 seconds" に対応
            print(f"error: request timed out after {args.timeout:.0f} seconds", file=sys.stderr)
            sys.exit(1)
    finally:
        await http.aclose()

    print(answer)


if __name__ == "__main__":
    main()

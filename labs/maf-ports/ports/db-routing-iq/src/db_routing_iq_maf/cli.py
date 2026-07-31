"""CLI エントリポイント(元アプリの Streamlit UI の置き換え)。

    uv run db-routing-iq-maf "Aurora X10 の重さとバッテリー持続時間は?"
    uv run db-routing-iq-maf --json "返品は何日以内に申請すればいいですか?"

前提: 共有基盤の Foundry 設定+本ポート infra の AZURE_SEARCH_*
(labs/maf-ports/.env)+ ``scripts/setup_kb.py`` 実行済み(knowledge base
が存在すること)。

``async with agent:`` が MCP 接続のライフサイクルを担う(enter で initialize +
tools/list、exit で切断)。api-key ヘッダー付き httpx クライアントと DDG 用
クライアントの後始末はこちら(finally)の責務。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .agents import build_chat_client, build_routing_agent
from .config import ConfigError, DbRoutingIqSettings
from .observability import setup_tracing
from .query import DEFAULT_TIMEOUT_SECONDS, response_text, run_query, summarize_tool_calls
from .search import default_http_client
from .tools import build_kb_mcp_tool, make_http_client, make_web_search_tool


def main() -> None:
    parser = argparse.ArgumentParser(
        description="複数ナレッジソース振り分け QA(MAF + Foundry IQ 移植版)"
    )
    parser.add_argument(
        "question",
        help="質問(例: 'Aurora X10 の重さとバッテリー持続時間は?')",
    )
    parser.add_argument("--json", action="store_true", help="回答とツール呼び出しを JSON で出す")
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"全体タイムアウト秒(既定 {DEFAULT_TIMEOUT_SECONDS:.0f})",
    )
    args = parser.parse_args()
    try:
        asyncio.run(_run(args))
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)


async def _run(args: argparse.Namespace) -> None:
    settings = DbRoutingIqSettings.from_env()
    if setup_tracing(settings.app_insights_connection_string):
        print("tracing: App Insights 有効", file=sys.stderr)

    print(f"[kb] {settings.kb_mcp_url}", file=sys.stderr)

    kb_http = make_http_client(settings)
    web_http = default_http_client()
    try:
        kb_tool = build_kb_mcp_tool(settings, kb_http)
        agent = build_routing_agent(
            build_chat_client(settings), kb_tool, make_web_search_tool(web_http)
        )
        try:
            async with agent:  # enter で MCP 接続、exit で切断
                response = await run_query(agent, args.question, timeout=args.timeout)
        except TimeoutError:
            print(f"error: request timed out after {args.timeout:.0f} seconds", file=sys.stderr)
            sys.exit(1)
    finally:
        await web_http.aclose()
        await kb_http.aclose()

    answer = response_text(response)
    tool_calls = summarize_tool_calls(response)
    # 元アプリの st.success("Using ... routing")相当のルーティング観測
    print(f"[tools] {', '.join(tool_calls) if tool_calls else '(none)'}", file=sys.stderr)

    if args.json:
        print(
            json.dumps(
                {"question": args.question, "answer": answer, "tool_calls": tool_calls},
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    print(answer)


if __name__ == "__main__":
    main()

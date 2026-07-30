"""CLI エントリポイント(元アプリの Streamlit UI の置き換え)。

    uv run corrective-rag-maf "What is the Azure AI Search free tier limit?"
    uv run corrective-rag-maf --json "..."      # 全出力を JSON で
    uv run corrective-rag-maf --top-k 6 "..."   # 検索件数の変更(既定 4)

前提: scripts/setup_index.py でインデックス作成+文書投入済みであること。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from functools import partial

from .agents import build_agents, build_chat_client
from .config import ConfigError, CorrectiveRagSettings
from .observability import setup_tracing
from .retrieval import DEFAULT_TOP_K, make_azure_search_retriever
from .search import ddg_search, default_http_client
from .workflow import (
    WEB_SEARCH_MAX_RESULTS,
    CorrectiveRagResult,
    DocsRetrieved,
    GradeDecided,
    QueryRewritten,
    WebSearched,
    build_corrective_rag_workflow,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Corrective RAG(MAF + Foundry + Azure AI Search 移植版)"
    )
    parser.add_argument(
        "question",
        help="質問(例: 'What are the limits of the Azure AI Search free tier?')",
    )
    parser.add_argument("--json", action="store_true", help="全出力を JSON で出す")
    parser.add_argument(
        "--top-k", type=int, default=DEFAULT_TOP_K, help="ベクトル検索の取得件数(既定 4)"
    )
    args = parser.parse_args()
    try:
        asyncio.run(_run(args))
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)


async def _run(args: argparse.Namespace) -> None:
    settings = CorrectiveRagSettings.from_env()
    if setup_tracing(settings.app_insights_connection_string):
        print("tracing: App Insights 有効", file=sys.stderr)

    http = default_http_client()
    retriever, search_adapter = make_azure_search_retriever(settings, top_k=args.top_k)
    try:
        agents = build_agents(build_chat_client(settings))
        workflow = build_corrective_rag_workflow(
            agents,
            retriever,
            partial(_web_search, http),
        )

        result: CorrectiveRagResult | None = None
        async for event in workflow.run(args.question, stream=True):
            if event.type == "intermediate":
                _print_progress(event.data)
            elif event.type == "output":
                result = event.data
    finally:
        await search_adapter.aclose()
        await http.aclose()

    if result is None:
        print("error: workflow produced no answer", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return

    print(result.answer)
    if result.corrected:
        print(
            f"\n(corrective path: query rewritten to '{result.question}', "
            f"web results: {result.web_result_count})",
            file=sys.stderr,
        )


def _print_progress(data: object) -> None:
    """元アプリの "~-retrieve-~" 等の進捗ログ相当。"""
    if isinstance(data, DocsRetrieved):
        print(f"[retrieve] {data.count} docs", file=sys.stderr)
    elif isinstance(data, GradeDecided):
        decision = "transform query + web search" if data.run_web_search else "generate"
        print(
            f"[grade] kept={data.kept} dropped={data.dropped} → {decision}",
            file=sys.stderr,
        )
    elif isinstance(data, QueryRewritten):
        print(f"[transform_query] '{data.original}' → '{data.rewritten}'", file=sys.stderr)
    elif isinstance(data, WebSearched):
        status = "failed" if data.failed else f"{data.result_count} results"
        print(f"[web_search] {status}", file=sys.stderr)


async def _web_search(http, query: str):
    return await ddg_search(http, query, WEB_SEARCH_MAX_RESULTS)


if __name__ == "__main__":
    main()

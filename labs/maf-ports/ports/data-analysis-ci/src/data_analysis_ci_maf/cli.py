"""CLI エントリポイント(元アプリの Streamlit UI の置き換え)。

    uv run data-analysis-ci-maf data/sample_sales.csv "月別売上の傾向は?"
    uv run data-analysis-ci-maf data.xlsx "合計売上と上位カテゴリは?" --no-code
    uv run data-analysis-ci-maf data.csv "..." --timeout 600

前提: 共有基盤の Foundry 設定(labs/maf-ports/.env)。DuckDB も pandas も
ローカルには不要 — 分析コードはサーバー側の Code Interpreter コンテナで
実行される(コンテナはセッション課金。README の注意参照)。

フロー: ファイル検証 → Files API アップロード(chat client 内包の
AsyncOpenAI を再利用)→ code_interpreter ツール dict 組み立て → Agent 実行
→ 回答と「実行されたコード / 実行結果ログ」を表示(元アプリの
「💡 Check your terminal for a clearer output」がここでは一次出力になる)。
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from .agents import build_analyst_agent, build_chat_client
from .analysis import DEFAULT_TIMEOUT_SECONDS, build_analysis_prompt, run_analysis
from .config import ConfigError, FoundrySettings
from .datafile import UnsupportedFileError, upload_data_file, validate_data_file
from .observability import setup_tracing
from .tools import CodeInterpreterUnsupportedError, build_code_interpreter_tool


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CSV/Excel の自然言語分析(MAF + Foundry Code Interpreter 移植版)"
    )
    parser.add_argument("file", help="分析対象のデータファイル(.csv / .xlsx)")
    parser.add_argument("question", help="質問(例: '月別売上の傾向は?')")
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"全体タイムアウト秒(既定 {DEFAULT_TIMEOUT_SECONDS:.0f}。"
        "コンテナ起動+コード実行を含む)",
    )
    parser.add_argument(
        "--no-code",
        action="store_true",
        help="サンドボックスで実行されたコード・ログの表示を省略",
    )
    args = parser.parse_args()
    try:
        asyncio.run(_run(args))
    except (ConfigError, UnsupportedFileError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    except CodeInterpreterUnsupportedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)


async def _run(args: argparse.Namespace) -> None:
    settings = FoundrySettings.from_env()
    if setup_tracing(settings.app_insights_connection_string):
        print("tracing: App Insights 有効", file=sys.stderr)

    data_path = validate_data_file(args.file)
    chat_client = build_chat_client(settings)

    print(f"[upload] {data_path.name} → Files API", file=sys.stderr)
    file_id = await upload_data_file(chat_client.client.files, data_path)
    print(f"[upload] file id: {file_id}", file=sys.stderr)

    tool = build_code_interpreter_tool(chat_client, [file_id])
    agent = build_analyst_agent(chat_client, tool)
    prompt = build_analysis_prompt(args.question, data_path.name)

    try:
        result = await run_analysis(agent, prompt, timeout=args.timeout)
    except TimeoutError:
        print(f"error: request timed out after {args.timeout:.0f} seconds", file=sys.stderr)
        sys.exit(1)

    print(result.text)
    if not args.no_code:
        for index, code in enumerate(result.code_blocks, start=1):
            print(f"\n--- 実行コード {index}(Code Interpreter)---")
            print(code)
        for index, log in enumerate(result.logs, start=1):
            print(f"\n--- 実行結果 {index} ---")
            print(log)
    for uri in result.image_uris:
        print(f"\n[生成画像] {uri}", file=sys.stderr)


if __name__ == "__main__":
    main()

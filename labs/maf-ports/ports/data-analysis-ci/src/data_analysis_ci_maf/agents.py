"""データ分析エージェントの組み立て(元アプリの agno Agent に対応)。

元(ai_data_analyst.py 86-91 行): ``Agent(model=OpenAIChat("gpt-4o"),
tools=[duckdb_tools, PandasTools()], system_message="You are an expert data
analyst. Use the 'uploaded_data' table ... Generate SQL queries using DuckDB
tools ...", markdown=True)``。

移植後: 同じ単一役割を MAF ``Agent`` として作る。system_message の骨格
(expert data analyst / 対象データの指定 / 手段の指定 / 簡潔な回答)は保ち、
手段だけを「DuckDB の SQL」から「Code Interpreter 上の Python(pandas)」に
置き換える。「'uploaded_data' テーブル」に相当する対象データの指定は、
per-run のプロンプト(analysis.py の build_analysis_prompt)がファイル名で
行う。ツール dict は通常ツールとして ``agent.default_options["tools"]`` に
載る(MCP ツールのような分離保持・接続ライフサイクルはない —
サーバー側ツールなのでクライアントに接続すべきものがない)。
"""

from __future__ import annotations

from typing import Any, Protocol

from .config import FoundrySettings

#: 元アプリの system_message の移植(DuckDB SQL → Code Interpreter の Python)
INSTRUCTIONS = """\
You are an expert data analyst. Use the uploaded data file to answer user queries.
Write and run Python (pandas) with the code interpreter to solve the user's query.
Parse dates and coerce numeric columns as needed before analysis.
Provide clear and concise answers with the results, using markdown formatting.
Present numerical results explicitly (totals, rankings, trends) rather than vague summaries.
"""


class SupportsRun(Protocol):
    """分析実行が必要とする最小面: ``await run(text)`` → ``.text`` /
    ``.messages`` を持つ応答。テストでは scripted fake が置き換える。"""

    async def run(self, message: str) -> Any: ...


def build_chat_client(settings: FoundrySettings) -> Any:
    from agent_framework.openai import OpenAIChatClient

    return OpenAIChatClient(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.openai_v1_endpoint,
    )


def build_analyst_agent(chat_client: Any, code_interpreter_tool: Any) -> SupportsRun:
    from agent_framework import Agent

    return Agent(
        chat_client,
        name="data_analyst",
        instructions=INSTRUCTIONS,
        tools=[code_interpreter_tool],
    )

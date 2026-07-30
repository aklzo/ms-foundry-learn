"""3 役割エージェントの組み立て(元アプリの LLM 呼び出しに対応)。

元(LangChain + LangGraph): ノード関数ごとに ``ChatAnthropic(model=
"claude-sonnet-4-5", temperature=0, max_tokens=1000)`` を作り、
PromptTemplate 全文を 1 メッセージとして invoke していた(system prompt
なし)。役割は 3 つ:

- grade_documents: 文書ごとの関連度採点({"score": "yes"/"no"} の JSON)
- transform_query: 検索最適化クエリへの書換
- generate: コンテキスト+質問からの回答生成

移植後: 同じ 3 役割を MAF ``Agent`` として作る。元に system prompt が
ないことに合わせて instructions は与えず、元 PromptTemplate の原文は
workflow.py の各 Executor が実行メッセージとして組み立てる。grader だけ
``ChatOptions(response_format=GradeScore)`` を付け、元の「JSON を regex で
拾う」パースをネイティブ構造化出力+lenient フォールバックに強化する。
モデルは Foundry のデプロイ(既定 gpt-5.4-mini)を 3 役割で共用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .config import CorrectiveRagSettings
from .schemas import GradeScore


class SupportsRun(Protocol):
    """workflow が必要とする最小面: ``await run(text)`` → ``.text``(と、
    構造化出力では ``.value``)を持つ応答。テストでは scripted fake が
    置き換える。"""

    async def run(self, message: str) -> Any: ...


@dataclass
class CorrectiveRagAgents:
    grader: SupportsRun
    rewriter: SupportsRun
    generator: SupportsRun


def build_chat_client(settings: CorrectiveRagSettings) -> Any:
    from agent_framework.openai import OpenAIChatClient

    return OpenAIChatClient(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.openai_v1_endpoint,
    )


def build_agents(chat_client: Any) -> CorrectiveRagAgents:
    """3 役割を組み立てる。grader はネイティブ構造化出力付き。"""
    from agent_framework import Agent, ChatOptions

    return CorrectiveRagAgents(
        grader=Agent(
            chat_client,
            name="grader_agent",
            default_options=ChatOptions(response_format=GradeScore),
        ),
        rewriter=Agent(chat_client, name="rewriter_agent"),
        generator=Agent(chat_client, name="generator_agent"),
    )

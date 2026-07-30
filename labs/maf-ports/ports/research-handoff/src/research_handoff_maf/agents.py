"""3 役割エージェントの組み立て(元アプリの Agent 定義に対応)。

元(OpenAI Agents SDK): triage_agent(output_type=ResearchPlan +
handoffs=[research, editor])/ research_agent(WebSearchTool +
save_important_fact)/ editor_agent(output_type=ResearchReport)を
すべて gpt-4o-mini で作り、Runner.run を 2 回(triage → 手動で editor)。

移植後: 同じ 3 役割を MAF ``Agent`` として作り、handoff は triage の
構造化出力(TriageDecision)+ workflow.py の switch-case エッジで表現する。
instructions は原文をほぼ流用(差分は README の「元との差分」参照)。
モデルは Foundry のデプロイ(既定 gpt-5.4-mini)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from .config import FoundrySettings
from .schemas import ResearchReport, TriageDecision
from .tools import FactStore, make_save_fact_tool, make_search_tool


class SupportsRun(Protocol):
    """workflow が必要とする最小面: ``await run(text)`` → ``.text``(と、
    構造化出力では ``.value``)を持つ応答。テストでは scripted fake が
    置き換える。"""

    async def run(self, message: str) -> Any: ...


@dataclass
class ResearchHandoffAgents:
    triage: SupportsRun
    research: SupportsRun
    editor: SupportsRun


#: 元の triage_agent の instructions を流用。手順 3〜4 の「Hand off to ...」
#: (SDK の handoff ツール呼び出しを促す文)だけを、構造化出力で委譲先を
#: 返させる文に置き換えた。direct(editor 直行)分岐は、元アプリで
#: handoffs=[research, editor] と editor への直接委譲も宣言されていたことに
#: 対応する。
TRIAGE_INSTRUCTIONS = (
    "You are the coordinator of this research operation. Your job is to:\n"
    "1. Understand the user's research topic\n"
    "2. Create a research plan with the following elements:\n"
    "   - topic: A clear statement of the research topic\n"
    "   - search_queries: A list of 3-5 specific search queries that will help gather "
    "information\n"
    "   - focus_areas: A list of 3-5 key aspects of the topic to investigate\n"
    "3. Decide who to hand off to next:\n"
    '   - "research": the topic needs fresh, factual, or fast-moving information '
    "gathered from the web (news, prices, product comparisons, recent events)\n"
    '   - "editor": the topic is stable, well-established knowledge that can be '
    "covered accurately without web research\n"
    "\n"
    "Return your decision in the expected structured format with plan (topic, "
    "search_queries, focus_areas), handoff_to, and a one-sentence reason."
)

#: 元の research_agent の instructions を流用。単発の検索語でなく計画
#: (複数クエリ)を受け取るため冒頭を調整し、ツール名の明示
#: (search_web / save_important_fact)を追加した。
RESEARCH_INSTRUCTIONS = (
    "You are a research assistant. Given a research plan with search queries, you "
    "search the web for each query and produce a concise summary of the results. The "
    "summary must be 2-3 paragraphs and less than 300 words. Capture the main points. "
    "Write succinctly, no need to have complete sentences or good grammar. This will "
    "be consumed by someone synthesizing a report, so it's vital you capture the "
    "essence and ignore any fluff. Use the search_web tool for each query, and record "
    "key findings with the save_important_fact tool as you go (include the source "
    "URL). Do not include any additional commentary other than the summary itself."
)

#: 元の editor_agent の instructions をそのまま流用。
EDITOR_INSTRUCTIONS = (
    "You are a senior researcher tasked with writing a cohesive report for a research "
    "query. You will be provided with the original query, and some initial research "
    "done by a research assistant.\n"
    "You should first come up with an outline for the report that describes the "
    "structure and flow of the report. Then, generate the report and return that as "
    "your final output.\n"
    "The final output should be in markdown format, and it should be lengthy and "
    "detailed. Aim for 5-10 pages of content, at least 1000 words."
)


def build_chat_client(settings: FoundrySettings) -> Any:
    from agent_framework.openai import OpenAIChatClient

    return OpenAIChatClient(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.openai_v1_endpoint,
    )


def build_agents(
    chat_client: Any, http: httpx.AsyncClient, fact_store: FactStore
) -> ResearchHandoffAgents:
    """3 役割を組み立てる。triage / editor は元の ``output_type=`` に対応する
    ネイティブ構造化出力(``ChatOptions(response_format=...)``)付き。"""
    from agent_framework import Agent, ChatOptions

    return ResearchHandoffAgents(
        triage=Agent(
            chat_client,
            instructions=TRIAGE_INSTRUCTIONS,
            name="triage_agent",
            default_options=ChatOptions(response_format=TriageDecision),
        ),
        research=Agent(
            chat_client,
            instructions=RESEARCH_INSTRUCTIONS,
            name="research_agent",
            tools=[make_search_tool(http), make_save_fact_tool(fact_store)],
        ),
        editor=Agent(
            chat_client,
            instructions=EDITOR_INSTRUCTIONS,
            name="editor_agent",
            default_options=ChatOptions(response_format=ResearchReport),
        ),
    )

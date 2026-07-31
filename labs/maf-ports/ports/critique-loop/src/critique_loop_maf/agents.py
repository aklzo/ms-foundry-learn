"""4 役割エージェントの組み立て(元アプリの LLM 呼び出しに対応)。

元(Groq SDK 直書き): 全役割が同一モデル(openai/gpt-oss-120b)で、役割の
違いは **temperature だけ**だった:

- 候補生成 ×3(temperature=0.9 — 多様性)
- 統合(0.2)/ 批評(0.3)/ 改訂(0.2)— system prompt はどの役割にもなし

移植後: gpt-5.4-mini(reasoning 系)は temperature を受け付けないため
(tech-selection-guide §2-6、Port 2 で確立した翻訳)、候補の多様性は
**観点ペルソナ(instructions)差**に置き換える。統合/批評/改訂は元どおり
instructions なしで、元 PromptTemplate の原文は workflow.py の各 Executor が
実行メッセージとして組み立てる。批評だけ ``ChatOptions(response_format=
CritiqueVerdict)`` を付け、元の「'•' 箇条書きを自由テキストで返す」を
ネイティブ構造化出力(継続/終了判断+改善指示)+lenient フォールバックに
強化する(corrective-rag の grader と同じ型)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .config import FoundrySettings
from .schemas import CritiqueVerdict


class SupportsRun(Protocol):
    """workflow が必要とする最小面: ``await run(text)`` → ``.text``(と、
    構造化出力では ``.value``)を持つ応答。テストでは scripted fake が
    置き換える。"""

    async def run(self, message: str) -> Any: ...


@dataclass
class Candidate:
    """名前付き候補生成役(名前は executor id・進捗イベントに使う)。"""

    name: str
    agent: SupportsRun


@dataclass
class CritiqueLoopAgents:
    candidates: list[Candidate]
    synthesizer: SupportsRun
    critic: SupportsRun
    reviser: SupportsRun


#: 候補生成 3 体の観点ペルソナ。元アプリの「同一プロンプト× temperature=0.9
#: を 3 回」による多様性を、観点(instructions)差に置き換える(Port 2 と
#: 同じ翻訳。3 体という数は元実装の並列候補数に合わせる)。
CANDIDATE_ANGLES: tuple[tuple[str, str], ...] = (
    (
        "structured",
        (
            "Answer the user's prompt with a rigorous, well-structured response. "
            "Prioritize completeness and correct terminology, and organize the answer "
            "with clear sections."
        ),
    ),
    (
        "practical",
        (
            "Answer the user's prompt with a practical, example-driven response. "
            "Prefer concrete code or worked examples and actionable steps over theory."
        ),
    ),
    (
        "skeptical",
        (
            "Answer the user's prompt while actively covering edge cases, common "
            "mistakes, and trade-offs that a straightforward answer would miss."
        ),
    ),
)


def build_chat_client(settings: FoundrySettings) -> Any:
    from agent_framework.openai import OpenAIChatClient

    return OpenAIChatClient(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.openai_v1_endpoint,
    )


def build_agents(chat_client: Any) -> CritiqueLoopAgents:
    """4 役割を組み立てる(chat client は共有)。critic はネイティブ構造化
    出力付き。"""
    from agent_framework import Agent, ChatOptions

    candidates = [
        Candidate(
            name=name,
            agent=Agent(chat_client, name=f"candidate_{name}", instructions=instructions),
        )
        for name, instructions in CANDIDATE_ANGLES
    ]
    return CritiqueLoopAgents(
        candidates=candidates,
        synthesizer=Agent(chat_client, name="synthesizer_agent"),
        critic=Agent(
            chat_client,
            name="critic_agent",
            default_options=ChatOptions(response_format=CritiqueVerdict),
        ),
        reviser=Agent(chat_client, name="reviser_agent"),
    )

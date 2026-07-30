"""proposer 群+アグリゲータの組み立て(元アプリのモデル定義に対応)。

元(Together SDK 直書き): reference_models 4 種(Qwen2-72B / Qwen1.5-72B /
Mixtral-8x22B / DBRX)へ同一質問を並列送信し、Mixtral-8x22B が固定 system
prompt で統合。
移植後: 共有基盤には gpt-5.4-mini しかデプロイされていないため、既定は
「同一モデル×ペルソナ違いの proposer 4体」(self-MoA)。環境変数
``FOUNDRY_PROPOSER_MODELS`` にカンマ区切りでデプロイ名を並べると
「1 モデル = 1 proposer」のモデル多様性モード(本来の MoA)に切り替わる。
元の temperature=0.7 による多様性は gpt-5 系(reasoning モデル)が
temperature 指定を受け付けないため採用せず、ペルソナ(instructions)差で
置き換えた。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from .config import FoundrySettings


class SupportsRun(Protocol):
    """workflow が必要とする最小面: ``await run(text)`` → ``.text`` を持つ応答。
    テストでは scripted fake が置き換える。"""

    async def run(self, message: str) -> Any: ...


@dataclass
class Proposer:
    """名前付き proposer(名前は executor id・進捗イベント・集約プロンプトに使う)。"""

    name: str
    agent: SupportsRun


@dataclass
class MoAAgents:
    proposers: list[Proposer]
    aggregator: SupportsRun


#: 単一モデルモードのペルソナ(名前, instructions)。多様性の源泉を
#: モデル差からプロンプト差に置き換える。
PERSONAS: tuple[tuple[str, str], ...] = (
    (
        "analyst",
        (
            "You are a rigorous analyst. Answer the user's question with precise, "
            "well-structured reasoning. Prioritize factual accuracy, define key terms, "
            "and state your confidence when evidence is thin."
        ),
    ),
    (
        "creative",
        (
            "You are a creative thinker. Answer the user's question by exploring "
            "unconventional angles, analogies, and alternative framings that a "
            "straightforward answer would miss. Stay relevant to the question."
        ),
    ),
    (
        "skeptic",
        (
            "You are a constructive skeptic. Answer the user's question while actively "
            "looking for common misconceptions, edge cases, and reasons the obvious "
            "answer could be wrong. Correct likely errors explicitly."
        ),
    ),
    (
        "pragmatist",
        (
            "You are a pragmatist. Answer the user's question with a focus on "
            "actionable guidance: concrete steps, trade-offs, and what to do first. "
            "Keep theory to the minimum needed."
        ),
    ),
)

#: モデル多様性モード(FOUNDRY_PROPOSER_MODELS 指定時)の共通 instructions。
#: 多様性はモデル差から得るので、プロンプトは中立にする。
NEUTRAL_PROPOSER_INSTRUCTIONS = (
    "Answer the user's question with your best, complete response. "
    "Show clear reasoning and structure. Do not defer to other models or sources."
)

#: 元アプリの aggregator_system_prompt をそのまま移植(末尾の
#: "Responses from models:" ラベルだけ user message 側に移した)。
AGGREGATOR_INSTRUCTIONS = (
    "You have been provided with a set of responses from various open-source models "
    "to the latest user query. Your task is to synthesize these responses into a "
    "single, high-quality response. It is crucial to critically evaluate the "
    "information provided in these responses, recognizing that some of it may be "
    "biased or incorrect. Your response should not simply replicate the given "
    "answers but should offer a refined, accurate, and comprehensive reply to the "
    "instruction. Ensure your response is well-structured, coherent, and adheres to "
    "the highest standards of accuracy and reliability."
)


@dataclass(frozen=True)
class ProposerSpec:
    """proposer 1体分の構成(純データ。テストはここまでで検証できる)。"""

    name: str
    model: str
    instructions: str


def _slug(model: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", model).strip("-").lower() or "model"


def build_proposer_specs(settings: FoundrySettings) -> list[ProposerSpec]:
    """モデルが1つならペルソナ4体、複数指定なら1モデル=1 proposer。"""
    models = settings.proposer_models or (settings.model,)
    if len(models) == 1:
        return [
            ProposerSpec(name=name, model=models[0], instructions=instructions)
            for name, instructions in PERSONAS
        ]
    return [
        ProposerSpec(
            name=f"m{i}-{_slug(model)}",
            model=model,
            instructions=NEUTRAL_PROPOSER_INSTRUCTIONS,
        )
        for i, model in enumerate(models, start=1)
    ]


def build_chat_client(settings: FoundrySettings, model: str | None = None) -> Any:
    from agent_framework.openai import OpenAIChatClient

    return OpenAIChatClient(
        model=model or settings.model,
        api_key=settings.api_key,
        base_url=settings.openai_v1_endpoint,
    )


def build_agents(settings: FoundrySettings) -> MoAAgents:
    """proposer 群+アグリゲータを組み立てる(chat client はモデル単位で共有)。"""
    from agent_framework import Agent

    clients: dict[str, Any] = {}

    def client_for(model: str) -> Any:
        if model not in clients:
            clients[model] = build_chat_client(settings, model)
        return clients[model]

    proposers = [
        Proposer(
            name=spec.name,
            agent=Agent(
                client_for(spec.model),
                instructions=spec.instructions,
                name=spec.name,
            ),
        )
        for spec in build_proposer_specs(settings)
    ]
    aggregator = Agent(
        client_for(settings.aggregator_model or settings.model),
        instructions=AGGREGATOR_INSTRUCTIONS,
        name="aggregator",
    )
    return MoAAgents(proposers=proposers, aggregator=aggregator)

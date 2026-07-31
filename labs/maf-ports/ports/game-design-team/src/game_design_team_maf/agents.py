"""4 役割エージェントの組み立て(元アプリの SwarmAgent 定義に対応)。

元(AG2 旧 Swarm API): ``SwarmAgent`` ×4(story / gameplay / visuals / tech)。
各エージェントは update_*_overview 関数(context 書き込み+SwarmResult で次の
エージェントを指名)と ``UPDATE_SYSTEM_MESSAGE``(毎ターンの system prompt
差し替え)を持ち、``register_hand_off(AFTER_WORK(next))`` でリングを構成、
``initiate_swarm_chat(initial_agent=story, max_rounds=13)`` で実行していた。

移植後: 同じ 4 役割を MAF ``Agent`` として作る。役割ペルソナ
(system_messages 原文)は静的 instructions に置き、フェーズ別の動的部分は
prompts.py が実行のたびに組み立てて run に渡す。リング・context 書き込み・
終了判定はすべて workflow.py のグラフ側が決定的に担う。
モデルは Foundry のデプロイ(既定 gpt-5.4-mini)を 4 役割で共用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .config import FoundrySettings
from .prompts import SYSTEM_MESSAGES


class SupportsRun(Protocol):
    """workflow が必要とする最小面: ``await run(text)`` → ``.text`` を持つ応答。
    テストでは scripted fake が置き換える。"""

    async def run(self, message: str) -> Any: ...


@dataclass
class GameDesignAgents:
    story: SupportsRun
    gameplay: SupportsRun
    visuals: SupportsRun
    tech: SupportsRun

    def for_role(self, role: str) -> SupportsRun:
        return getattr(self, role)


def build_chat_client(settings: FoundrySettings) -> Any:
    from agent_framework.openai import OpenAIChatClient

    return OpenAIChatClient(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.openai_v1_endpoint,
    )


def build_agents(chat_client: Any) -> GameDesignAgents:
    """4 役割を組み立てる。instructions は元の system_messages 原文。

    元アプリと違いツールは持たない: update_*_overview(context 書き込み+
    ルーティング)は LLM の関数呼び出しではなく、workflow.py の Executor が
    決定的に行うため。
    """
    from agent_framework import Agent

    def role_agent(role: str) -> Any:
        return Agent(
            chat_client,
            instructions=SYSTEM_MESSAGES[role],
            name=f"{role}_agent",
        )

    return GameDesignAgents(
        story=role_agent("story"),
        gameplay=role_agent("gameplay"),
        visuals=role_agent("visuals"),
        tech=role_agent("tech"),
    )

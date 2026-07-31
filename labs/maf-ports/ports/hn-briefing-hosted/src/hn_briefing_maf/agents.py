"""ブリーフ生成エージェント(ワークフローの LLM 段)の組み立て。

元アプリの ADK ``LlmAgent``(agent.py)の instructions を核に、
「digest を受け取って編集する」ワークフロー用に再構成した。ペルソナ・
簡潔さ・observation と delivery の分離(送信したと主張しない)は元の
文言を踏襲。ランキングは決定論段の責務なので **並び替え禁止**を明記する。
"""

from __future__ import annotations

from typing import Any, Protocol

from .config import FoundrySettings

#: 元 agent.py の instruction(AgentScout ペルソナ+運用規約)を
#: digest 編集用に移植したもの。
BRIEFING_INSTRUCTIONS = """\
You are AgentScout, an always-on Hacker News briefing agent for teams building
AI agents and LLM apps.

You receive a deterministically ranked digest of today's highest-signal
Hacker News stories (title, signal note, points/comments/front-page rank, and
links). Write a concise engineering brief in markdown:

- One section per story, in the exact order of the digest (the ranking is
  deterministic — never reorder, drop, or add stories).
- For each story: 2-3 sentences on why it matters to engineers and product
  builders (architecture, tooling, or workflow ideas), then the source and HN
  discussion links from the digest.
- End with a "Next actions" section: 2-3 operational bullet points grounded in
  today's stories.
- Separate observation from delivery; do not claim to send messages or
  schedule jobs.
- Keep responses concise and operational. Prefer ranked findings, signal, and
  next actions.
"""


class SupportsRun(Protocol):
    """ワークフローが必要とする最小面: ``await run(text)`` → ``.text`` を持つ
    応答。テストでは scripted fake が置き換える。"""

    async def run(self, message: str) -> Any: ...


def build_chat_client(settings: FoundrySettings) -> Any:
    """クライアント実行(CLI)用のチャットクライアント。

    共有基盤の OpenAI v1 互換エンドポイント+API キー。hosted agent 側は
    hosting/main.py が FoundryChatClient + agent identity で作る(README の
    学び「実行点と資格情報の置き場所」参照)。
    """
    from agent_framework.openai import OpenAIChatClient

    return OpenAIChatClient(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.openai_v1_endpoint,
    )


def build_briefing_agent(chat_client: Any) -> SupportsRun:
    """digest からブリーフ本文を書く単発エージェント(ツールなし)。"""
    from agent_framework import Agent

    return Agent(
        chat_client,
        name="hn_briefing_writer",
        instructions=BRIEFING_INSTRUCTIONS,
    )

"""hosted agent 用のエージェント組み立て(元 agent.py の LlmAgent + tool 相当)。

hosted agent は Responses protocol の**会話面**なので、ワークフローの
決定論パイプライン(収集+ランキング)を **1 個の関数ツール**として持つ
エージェントに再編する — 元 ADK 実装(LlmAgent + preview_agent_builder_brief
ツール)と同じ形に戻る構図。

**ツール直付け不可の制約(tech-selection-guide §4 / survey features/03)への
設計判断**: hosted agent はエージェント**定義**にツールを付けられず Toolbox
(MCP)経由が前提だが、それは Foundry 管理ツールの話。本ポートのツールは
HN Algolia へのキーレス GET 1 本なので、**コンテナ内で動く MAF の関数ツール
(エージェント内部の httpx 呼び出し)**として実装すれば定義にツールを載せる
必要がそもそもない = 制約に該当しない。Toolbox が必要になるのは認証付き
Foundry ツール(Code Interpreter / Web Search 等)を使うときだけ。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from .briefing import render_digest
from .hn import fetch_front_page
from .ranking import DEFAULT_TOP_N, clamp_top_n, curate_stories

#: hosted 面の instructions(元 agent.py の instruction のツール規約を
#: collect_ranked_stories に差し替えたもの)。
HOSTED_INSTRUCTIONS = """\
You are AgentScout, an always-on Hacker News briefing agent for teams building
AI agents and LLM apps.

Your job is to act like a focused daily briefing system:
- When asked for the current brief, daily digest, scouting run, or Hacker News
  update, call the collect_ranked_stories tool first. It fetches today's
  Hacker News front page and returns a deterministically ranked digest.
- Write the brief strictly from the digest the tool returns, in the exact
  order of the digest (never reorder, drop, or add stories).
- Explain why each item matters to engineers and product builders, then end
  with a "Next actions" section of 2-3 operational bullet points.
- Separate observation from delivery; do not claim to send messages or
  schedule jobs.
- Keep responses concise and operational. Prefer ranked findings, signal, and
  next actions.
"""


def make_collect_tool(http: httpx.AsyncClient) -> Callable[..., Any]:
    """収集+決定論ランキングを 1 本の関数ツールに包む(クロージャ注入)。"""

    async def collect_ranked_stories(top_n: int = DEFAULT_TOP_N) -> str:
        """Fetch today's Hacker News front page and return the top AI-agent
        stories as a deterministically ranked digest.

        Args:
            top_n: Number of stories to include (clamped to 1-10).
        """
        stories = await fetch_front_page(http)
        curated = curate_stories(stories, top_n=clamp_top_n(top_n))
        return render_digest(curated)

    return collect_ranked_stories


def build_hosted_briefing_agent(chat_client: Any, http: httpx.AsyncClient) -> Any:
    """hosted agent 本体(hosting/main.py が ResponsesHostServer に載せる)。

    ``default_options={"store": False}``: 会話履歴は Responses protocol の
    ホスティング基盤(conversation ID)が管理するため、モデル側の保存を
    切る(foundry-samples の 01-basic と同じ指定)。
    """
    from agent_framework import Agent

    return Agent(
        chat_client,
        name="hn_briefing_agent",
        instructions=HOSTED_INSTRUCTIONS,
        tools=[make_collect_tool(http)],
        default_options={"store": False},
    )

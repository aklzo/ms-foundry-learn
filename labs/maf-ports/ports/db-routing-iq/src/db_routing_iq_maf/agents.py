"""ルーティング付き QA エージェントの組み立て。

元アプリには「三段カスケード関数(route_query)+回答チェーン+fallback
エージェント」の 3 部品があったが、移植後は **単一の MAF Agent** に縮退する:

- 段 1(全 DB 閾値検索)+段 2(agno LLM ルート)→ knowledge base の
  agentic retrieval(MCP ツール ``knowledge_base_retrieve`` の内側)
- 段 3(LangGraph ReAct + DDG)→ 同じエージェントの ``web_search`` ツール
  (呼ぶかどうかの判断は instructions ベース)
- 回答生成(create_retrieval_chain の system prompt)→ instructions に移植

instructions は Foundry IQ 接続ガイドの推奨テンプレート(KB を必ず使う/
無ければ web / 出典を付ける)+元アプリの回答プロンプト(コンテキストに
厳密・簡潔)+元アプリの Web fallback の表示規約(``Web Search Result:``
プレフィックス)を合成したもの。
"""

from __future__ import annotations

from typing import Any, Protocol

from .config import DbRoutingIqSettings

#: 元アプリ対応: 回答規約は query_database の system prompt
#: (direct and concise / strictly on the provided context)、Web fallback の
#: 表示は _handle_web_fallback の "Web Search Result:" プレフィックスを踏襲。
INSTRUCTIONS = """\
You are a company knowledge assistant. The knowledge base behind the
knowledge_base_retrieve tool contains three sources: Product Information,
Customer Support & FAQ, and Financial Information. It routes each question to
the right source(s) automatically — always call knowledge_base_retrieve first
with the user's question.

- Base your answer strictly on the retrieved content. Be direct and concise.
  Mention which source documents (titles) the answer came from.
- If the retrieved content does not contain enough information to answer,
  acknowledge this limitation instead of guessing.
- Only if the knowledge base returns nothing relevant to the question, call the
  web_search tool and answer from the search results. Start such an answer with
  "Web Search Result:" so the reader knows it did not come from the knowledge
  base.
- Never invent facts that are in neither the knowledge base nor the search
  results.
"""


class SupportsRun(Protocol):
    """クエリ実行が必要とする最小面: ``await run(text)`` → ``.text`` を持つ
    応答。テストでは scripted fake が置き換える。"""

    async def run(self, message: str) -> Any: ...


def build_chat_client(settings: DbRoutingIqSettings) -> Any:
    from agent_framework.openai import OpenAIChatClient

    return OpenAIChatClient(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.openai_v1_endpoint,
    )


def build_routing_agent(chat_client: Any, kb_tool: Any, web_search_tool: Any) -> SupportsRun:
    """KB MCP ツール+Web fallback ツールを持つ単一エージェントを作る。

    MAF の Agent は MCPTool を通常ツールと分けて ``agent.mcp_tools`` に保持し、
    run 時に未接続なら接続してサーバーのツール群(knowledge_base_retrieve)を
    展開する。web_search は素の callable としてスキーマ推論される。
    """
    from agent_framework import Agent

    return Agent(
        chat_client,
        name="db_routing_agent",
        instructions=INSTRUCTIONS,
        tools=[kb_tool, web_search_tool],
    )

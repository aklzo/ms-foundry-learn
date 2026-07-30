"""1 ターンのチャットロジック — 元アプリの Streamlit ハンドラ本体の移植。

元アプリの毎ターンの順序(travel_agent_memory.py 69-99 行)を忠実に踏襲する:

1. ``memory.search(query=prompt, user_id)`` — 関連記憶を検索
2. ``"Relevant past information:\\n- ..."`` を組み立てプロンプトへ注入
3. ``chat.completions.create(...)`` — 応答生成(空応答は ValueError)
4. ``memory.add(prompt, role=user)`` → ``memory.add(answer, role=assistant)``
   — user / assistant の発言を **応答の後に** 2 回に分けて記憶へ追加

元アプリの quirk も保存する:

- 記憶が 0 件でも「Relevant past information:」ヘッダーは注入される
- 今ターンの発言は検索の後に add されるため、同一ターンの応答には反映され
  ない(次ターンから効く)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .agents import SupportsRun
from .memory import DEFAULT_MAX_MEMORIES, MemoryRecord, MemoryStore

#: 元アプリの context ヘッダー(原文のまま)
CONTEXT_HEADER = "Relevant past information:"


@dataclass
class TurnResult:
    """1 ターンの結果(CLI 表示・テスト・評価に使う)。"""

    answer: str
    prompt: str  # エージェントに実際に送った全文(記憶注入の検証用)
    memories: list[MemoryRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "prompt": self.prompt,
            "memories": [memory.content for memory in self.memories],
        }


def build_full_prompt(question: str, memories: list[MemoryRecord]) -> str:
    """元アプリのプロンプト連結(69-78 行)を原文どおり再現する。"""
    context = f"{CONTEXT_HEADER}\n"
    for memory in memories:
        context += f"- {memory.content}\n"
    return f"{context}\nHuman: {question}\nAI:"


async def run_turn(
    agent: SupportsRun,
    store: MemoryStore,
    user_id: str,
    question: str,
    *,
    max_memories: int = DEFAULT_MAX_MEMORIES,
) -> TurnResult:
    """検索 → 注入 → 応答 → 追加(元アプリと同じ順序)。"""
    memories = await store.search(question, user_id, limit=max_memories)
    full_prompt = build_full_prompt(question, memories)

    response = await agent.run(full_prompt)
    answer = getattr(response, "text", "") or ""
    if not answer:
        # 元アプリ 88-89 行: 空応答は ValueError(記憶へ追加しない)
        raise ValueError("Received empty or null response from the model")

    await store.add(question, user_id, role="user")
    await store.add(answer, user_id, role="assistant")
    return TurnResult(answer=answer, prompt=full_prompt, memories=memories)

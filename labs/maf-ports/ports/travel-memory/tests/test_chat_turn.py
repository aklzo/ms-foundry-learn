"""チャットターンのオフラインテスト。LLM は scripted fake、記憶ストアは
InMemoryFakeStore(+呼び出し記録ラッパ)。パターンは ports/corrective-rag/
tests/test_workflow.py の ScriptedAgent を踏襲。

検証項目(Port 5 の要点):
- 順序: 検索 → 注入 → 応答 → 追加(user → assistant)— 元アプリと同一
- 記憶ヒットが応答プロンプトに「Relevant past information:\\n- ...」形式で
  含まれること
- user_id スコープ分離(他ユーザーの記憶がプロンプトに漏れない)
- 元アプリの quirk: 記憶 0 件でもヘッダーは注入 / 空応答は ValueError で
  記憶に追加しない / 今ターンの発言は同一ターンの検索に反映されない
"""

from collections.abc import Sequence
from dataclasses import dataclass

import pytest

from travel_memory_maf.chat import CONTEXT_HEADER, build_full_prompt, run_turn
from travel_memory_maf.memory import DEFAULT_MAX_MEMORIES, InMemoryFakeStore, MemoryRecord

USER = "alice"


@dataclass
class FakeResponse:
    text: str


class ScriptedAgent:
    """受け取ったメッセージを記録し、決められた応答を順に返す
    (応答リストが尽きたら最後のものを繰り返す)。"""

    def __init__(self, replies: Sequence[str] = ("ok",)) -> None:
        self.replies = list(replies)
        self.received: list[str] = []

    async def run(self, message: str) -> FakeResponse:
        index = min(len(self.received), len(self.replies) - 1)
        self.received.append(message)
        return FakeResponse(text=self.replies[index])


class RecordingStore:
    """InMemoryFakeStore を包み、呼び出し順を記録する。"""

    def __init__(self) -> None:
        self.inner = InMemoryFakeStore()
        self.calls: list[tuple] = []

    async def search(self, query: str, user_id: str, limit: int = DEFAULT_MAX_MEMORIES):
        self.calls.append(("search", query, user_id, limit))
        return await self.inner.search(query, user_id, limit=limit)

    async def add(self, text: str, user_id: str, role: str = "user") -> None:
        self.calls.append(("add", text, user_id, role))
        await self.inner.add(text, user_id, role=role)

    async def get_all(self, user_id: str):
        self.calls.append(("get_all", user_id))
        return await self.inner.get_all(user_id)


async def test_turn_order_search_inject_respond_add() -> None:
    """元アプリの順序(検索→注入→応答→追加)を固定する。"""
    store = RecordingStore()
    agent = ScriptedAgent(replies=("Try Kyoto in spring.",))

    result = await run_turn(agent, store, USER, "Where should I go?")

    assert [call[0] for call in store.calls] == ["search", "add", "add"]
    # 応答(agent.run)は search の後・add の前 — add 時点で応答が確定している
    assert len(agent.received) == 1
    assert store.calls[1] == ("add", "Where should I go?", USER, "user")
    assert store.calls[2] == ("add", "Try Kyoto in spring.", USER, "assistant")
    assert result.answer == "Try Kyoto in spring."


async def test_memory_hits_are_injected_into_prompt() -> None:
    """前ターン由来の記憶が「Relevant past information」としてプロンプトに入る。"""
    store = RecordingStore()
    await store.inner.add("I prefer window seats on flights", USER)

    agent = ScriptedAgent(replies=("Noted, window seat it is.",))
    result = await run_turn(agent, store, USER, "Book me flights and window seats to Tokyo")

    prompt = agent.received[0]
    assert prompt == result.prompt
    assert prompt.startswith(f"{CONTEXT_HEADER}\n")
    assert "- I prefer window seats on flights\n" in prompt
    assert prompt.endswith("\nHuman: Book me flights and window seats to Tokyo\nAI:")
    assert [memory.content for memory in result.memories] == [
        "I prefer window seats on flights"
    ]


async def test_no_memories_still_injects_header() -> None:
    """元アプリの quirk: 記憶 0 件でもヘッダーだけのコンテキストが注入される。"""
    store = RecordingStore()
    agent = ScriptedAgent()

    result = await run_turn(agent, store, USER, "First message ever")

    assert agent.received[0] == f"{CONTEXT_HEADER}\n\nHuman: First message ever\nAI:"
    assert result.memories == []


async def test_current_turn_not_visible_to_same_turn_search() -> None:
    """今ターンの発言は検索(add より前)に反映されない — 次ターンから効く。"""
    store = RecordingStore()
    agent = ScriptedAgent(replies=("Sure.", "Sure again."))

    first = await run_turn(agent, store, USER, "I only travel with hand luggage")
    assert first.memories == []  # 自分自身はまだ記憶にない

    second = await run_turn(agent, store, USER, "What luggage should I bring, hand or checked?")
    assert any("hand luggage" in memory.content for memory in second.memories)
    assert "- I only travel with hand luggage\n" in agent.received[1]


async def test_user_scope_isolation_end_to_end() -> None:
    """alice の嗜好が bob のプロンプトに漏れない。"""
    store = RecordingStore()
    agent = ScriptedAgent(replies=("ok", "ok", "ok"))

    await run_turn(agent, store, "alice", "I am vegetarian and love street food")
    bob = await run_turn(agent, store, "bob", "Recommend street food, vegetarian if possible")

    assert bob.memories == []
    assert "vegetarian and love street food" not in agent.received[1]

    alice_again = await run_turn(agent, store, "alice", "Recommend street food, vegetarian ok?")
    assert any("vegetarian" in memory.content for memory in alice_again.memories)


async def test_empty_answer_raises_and_skips_memory_add() -> None:
    """元アプリ 88-89 行: 空応答は ValueError。記憶追加(add)は行われない。"""
    store = RecordingStore()
    agent = ScriptedAgent(replies=("",))

    with pytest.raises(ValueError):
        await run_turn(agent, store, USER, "hello")

    assert [call[0] for call in store.calls] == ["search"]


async def test_max_memories_is_passed_to_search() -> None:
    store = RecordingStore()
    agent = ScriptedAgent()

    await run_turn(agent, store, USER, "hello", max_memories=2)

    assert store.calls[0] == ("search", "hello", USER, 2)


def test_build_full_prompt_matches_original_format() -> None:
    """元アプリ 71-78 行の文字列連結を 1 文字単位で固定する。"""
    memories = [MemoryRecord(content="likes ramen"), MemoryRecord(content="hates crowds")]
    prompt = build_full_prompt("Where to eat?", memories)
    assert prompt == (
        "Relevant past information:\n"
        "- likes ramen\n"
        "- hates crowds\n"
        "\n"
        "Human: Where to eat?\n"
        "AI:"
    )

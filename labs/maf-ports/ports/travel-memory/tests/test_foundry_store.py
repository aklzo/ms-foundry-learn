"""FoundryMemoryStore の SDK 呼び出しマッピングのオフラインテスト。

azure-ai-projects の ``client.beta.memory_stores`` 互換のスタブを注入し、
ネットワークなしで以下を固定する:

- mem0 → Foundry の引数対応: user_id → scope、テキスト → Responses API の
  message item(role/type/content)、limit → MemorySearchOptions.max_memories
- add の LRO チェーン: scope ごとに previous_update_id が引き継がれる /
  別 scope はチェーンを共有しない / update_delay が伝わる
- wait_for_update=True のときだけ poller.result() を待つ
- search / get_all の応答 → MemoryRecord への写像
"""

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from travel_memory_maf.memory import FoundryMemoryStore, MemoryRecord

STORE_NAME = "travel_memory_test"


def _memory_item(content: str, kind: str = "user_profile", memory_id: str = "m1") -> Any:
    return SimpleNamespace(content=content, kind=kind, memory_id=memory_id)


@dataclass
class StubPoller:
    update_id: str
    waited: list[str] = field(default_factory=list)

    async def result(self) -> Any:
        self.waited.append(self.update_id)
        return SimpleNamespace(memory_operations=[])


class StubMemoryStores:
    """beta.memory_stores 互換の記録スタブ。"""

    def __init__(self) -> None:
        self.search_calls: list[dict] = []
        self.update_calls: list[dict] = []
        self.list_calls: list[dict] = []
        self.delete_scope_calls: list[dict] = []
        self.search_result_items: list[Any] = []
        self.list_result_items: list[Any] = []
        self.pollers: list[StubPoller] = []

    async def search_memories(self, **kwargs: Any) -> Any:
        self.search_calls.append(kwargs)
        return SimpleNamespace(
            search_id="s1",
            memories=[SimpleNamespace(memory_item=item) for item in self.search_result_items],
        )

    async def begin_update_memories(self, **kwargs: Any) -> StubPoller:
        self.update_calls.append(kwargs)
        poller = StubPoller(update_id=f"up_{len(self.update_calls)}")
        self.pollers.append(poller)
        return poller

    def list_memories(self, **kwargs: Any) -> Any:
        self.list_calls.append(kwargs)
        items = list(self.list_result_items)

        async def _iterate():
            for item in items:
                yield item

        return _iterate()

    async def delete_scope(self, **kwargs: Any) -> Any:
        self.delete_scope_calls.append(kwargs)
        return SimpleNamespace(deleted=True)


class StubProjectClient:
    def __init__(self) -> None:
        self.memory_stores = StubMemoryStores()
        self.beta = SimpleNamespace(memory_stores=self.memory_stores)
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def make_store(**kwargs: Any) -> tuple[FoundryMemoryStore, StubMemoryStores]:
    client = StubProjectClient()
    return FoundryMemoryStore(client, STORE_NAME, **kwargs), client.memory_stores


async def test_search_maps_arguments_and_results() -> None:
    store, stub = make_store()
    stub.search_result_items = [_memory_item("prefers window seats", "user_profile", "mem_1")]

    records = await store.search("seat preference?", "alice", limit=3)

    call = stub.search_calls[0]
    assert call["name"] == STORE_NAME
    assert call["scope"] == "alice"  # user_id → scope の 1:1 対応
    assert call["items"] == [
        {"role": "user", "type": "message", "content": "seat preference?"}
    ]
    assert call["options"].max_memories == 3
    assert records == [
        MemoryRecord(content="prefers window seats", kind="user_profile", memory_id="mem_1")
    ]


async def test_add_sends_message_item_with_role() -> None:
    store, stub = make_store()

    await store.add("I love ramen", "alice", role="user")
    await store.add("Noted!", "alice", role="assistant")

    assert stub.update_calls[0]["items"] == [
        {"role": "user", "type": "message", "content": "I love ramen"}
    ]
    assert stub.update_calls[1]["items"] == [
        {"role": "assistant", "type": "message", "content": "Noted!"}
    ]
    assert all(call["name"] == STORE_NAME for call in stub.update_calls)
    assert all(call["scope"] == "alice" for call in stub.update_calls)


async def test_add_chains_previous_update_id_per_scope() -> None:
    """LRO チェーン: 同一 scope は前回の update_id を引き継ぎ、別 scope は独立。"""
    store, stub = make_store()

    await store.add("turn 1", "alice")
    await store.add("turn 2", "alice")
    await store.add("bob turn 1", "bob")

    assert stub.update_calls[0]["previous_update_id"] is None
    assert stub.update_calls[1]["previous_update_id"] == "up_1"
    assert stub.update_calls[2]["previous_update_id"] is None  # bob は新チェーン


async def test_update_delay_defaults_to_immediate() -> None:
    """既定 update_delay=0(サービス既定の 300 秒 debounce を毎ターン add に合わせ無効化)。"""
    store, stub = make_store()
    await store.add("hello", "alice")
    assert stub.update_calls[0]["update_delay"] == 0

    delayed, delayed_stub = make_store(update_delay=60)
    await delayed.add("hello", "alice")
    assert delayed_stub.update_calls[0]["update_delay"] == 60


async def test_wait_for_update_awaits_lro_result() -> None:
    fire_and_forget, stub1 = make_store()
    await fire_and_forget.add("hello", "alice")
    assert stub1.pollers[0].waited == []  # 既定は fire-and-forget

    waiting, stub2 = make_store(wait_for_update=True)
    await waiting.add("hello", "alice")
    assert stub2.pollers[0].waited == ["up_1"]  # ライブスモーク用: 完了まで待つ


async def test_get_all_maps_list_memories() -> None:
    store, stub = make_store()
    stub.list_result_items = [
        _memory_item("summary of trip talk", "chat_summary", "mem_9"),
        _memory_item("prefers ryokan", "user_profile", "mem_10"),
    ]

    records = await store.get_all("alice")

    assert stub.list_calls[0] == {"name": STORE_NAME, "scope": "alice"}
    assert [record.content for record in records] == [
        "summary of trip talk",
        "prefers ryokan",
    ]
    assert records[0].kind == "chat_summary"


async def test_delete_all_calls_delete_scope_and_resets_chain() -> None:
    """mem0 delete_all → delete_scope。削除後の add は新しいチェーンで始まる。"""
    store, stub = make_store()
    await store.add("turn 1", "alice")

    await store.delete_all("alice")

    assert stub.delete_scope_calls == [{"name": STORE_NAME, "scope": "alice"}]

    await store.add("fresh turn", "alice")
    assert stub.update_calls[1]["previous_update_id"] is None


async def test_aclose_closes_client_and_owned_credential() -> None:
    client = StubProjectClient()

    class StubCredential:
        closed = False

        async def close(self) -> None:
            self.closed = True

    credential = StubCredential()
    store = FoundryMemoryStore(client, STORE_NAME, credential=credential)

    await store.aclose()

    assert client.closed
    assert credential.closed

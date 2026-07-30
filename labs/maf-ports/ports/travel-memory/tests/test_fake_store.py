"""InMemoryFakeStore の add/search セマンティクスのテスト(ネットワーク不要)。

フェイクは mem0 の意味論の最小近似: add は発言をそのまま保存、search は
単語重なりスコアの上位 limit 件、user_id ごとに完全分離。チャットループの
オフラインテスト(test_chat_turn.py)が依存する土台なので、ここで固定する。
"""

from travel_memory_maf.memory import InMemoryFakeStore


async def test_add_then_search_returns_relevant_record() -> None:
    store = InMemoryFakeStore()
    await store.add("I prefer window seats on long flights", "alice")
    await store.add("My favorite food is ramen", "alice")

    hits = await store.search("window seats please", "alice")

    assert [hit.content for hit in hits] == ["I prefer window seats on long flights"]


async def test_search_excludes_zero_overlap() -> None:
    store = InMemoryFakeStore()
    await store.add("I love hiking in the mountains", "alice")

    assert await store.search("budget hotels in Paris", "alice") == []


async def test_search_orders_by_overlap_score() -> None:
    store = InMemoryFakeStore()
    await store.add("beach holidays", "alice")
    await store.add("beach holidays in sunny Okinawa", "alice")

    hits = await store.search("sunny beach holidays in Okinawa", "alice")

    assert [hit.content for hit in hits] == [
        "beach holidays in sunny Okinawa",  # 重なり 4 語
        "beach holidays",  # 重なり 2 語
    ]


async def test_search_respects_limit() -> None:
    store = InMemoryFakeStore()
    for i in range(4):
        await store.add(f"travel note {i}", "alice")

    hits = await store.search("travel note", "alice", limit=2)

    assert len(hits) == 2


async def test_user_id_scope_isolation() -> None:
    """alice の記憶は bob の検索・一覧に決して現れない(Foundry の scope 分離に対応)。"""
    store = InMemoryFakeStore()
    await store.add("I am allergic to shellfish", "alice")

    assert await store.search("shellfish allergy", "bob") == []
    assert await store.get_all("bob") == []

    alice_hits = await store.search("shellfish allergy", "alice")
    assert [hit.content for hit in alice_hits] == ["I am allergic to shellfish"]


async def test_delete_all_clears_only_that_user() -> None:
    store = InMemoryFakeStore()
    await store.add("alice fact", "alice")
    await store.add("bob fact", "bob")

    await store.delete_all("alice")

    assert await store.get_all("alice") == []
    assert [record.content for record in await store.get_all("bob")] == ["bob fact"]


async def test_get_all_preserves_insertion_order_and_role() -> None:
    store = InMemoryFakeStore()
    await store.add("Where should I go in spring?", "alice", role="user")
    await store.add("Kyoto is lovely in spring.", "alice", role="assistant")

    records = await store.get_all("alice")

    assert [(record.content, record.kind) for record in records] == [
        ("Where should I go in spring?", "user"),
        ("Kyoto is lovely in spring.", "assistant"),
    ]
    assert all(record.memory_id for record in records)

"""ライブスモーク(実 Foundry Memory + 実モデル)。既定では除外され、
``uv run pytest -m live`` で実行する。要 labs/maf-ports/.env + ``az login``
(Memory API は Entra ID 認証のみ)。

**前提: Memory ストアが存在すること。** 事前に 1 回だけ実行しておく:

    uv run python scripts/setup_memory.py

確認項目(PORTING.md §4):
1. 実モデル+実 Memory ストアで「嗜好を伝える → 記憶抽出(LRO 完了まで
   待機)→ 検索でヒット → 次ターンのプロンプトに注入」が完走すること
2. トレースが App Insights に届くこと(このテストでは送信の有効化まで。
   到達確認は CLI 実行後に az monitor app-insights query で行う)

テスト scope は実行ごとに一意にし、終了時に delete_scope で掃除する
(共有ストアを汚さない)。記憶抽出は LLM 依存のため「検索がヒットする」
ことまでは保証されない — アサーションは応答の正常性と API の完走を主にする。
"""

import uuid

import pytest

from travel_memory_maf.config import ConfigError, TravelMemorySettings

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def settings() -> TravelMemorySettings:
    try:
        return TravelMemorySettings.from_env()
    except ConfigError as exc:
        pytest.skip(f"live 設定なし: {exc}")


async def test_memory_roundtrip_live(settings: TravelMemorySettings) -> None:
    from travel_memory_maf.agents import build_chat_client, build_travel_agent
    from travel_memory_maf.chat import CONTEXT_HEADER, run_turn
    from travel_memory_maf.memory import make_foundry_memory_store
    from travel_memory_maf.observability import setup_tracing

    setup_tracing(settings.app_insights_connection_string)

    user_id = f"smoke_{uuid.uuid4().hex[:12]}"  # 一意 scope(終了時に削除)
    store = make_foundry_memory_store(settings, wait_for_update=True)
    agent = build_travel_agent(build_chat_client(settings))

    try:
        # ターン 1: 嗜好を伝える(wait_for_update=True なので抽出 LRO 完了まで待つ)
        first = await run_turn(
            agent,
            store,
            user_id,
            "I always fly with window seats and I am vegetarian. Remember this.",
        )
        assert first.answer.strip()
        assert first.prompt.startswith(CONTEXT_HEADER)

        # 記憶が scope に入ったことを直接確認(get_all = list_memories)
        stored = await store.get_all(user_id)

        # ターン 2: 前ターンの嗜好が検索・注入されるか(抽出内容は LLM 依存の
        # ため、ヒット自体は soft check とし、注入形式と応答の正常性を固定する)
        second = await run_turn(
            agent, store, user_id, "Book a flight to Tokyo. What should I ask the airline for?"
        )
        assert second.answer.strip()
        assert len(second.answer) > 20
        if second.memories:
            assert any(f"- {memory.content}\n" in second.prompt for memory in second.memories)

        assert stored or second.memories, (
            "記憶がストアに現れない — setup_memory.py 済みか、store のモデルデプロイ名を確認"
        )
    finally:
        # 掃除: テスト scope の記憶を削除してからクライアントを閉じる
        try:
            await store.delete_all(user_id)
        finally:
            await store.aclose()

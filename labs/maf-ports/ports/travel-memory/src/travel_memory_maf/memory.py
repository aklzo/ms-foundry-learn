"""記憶ストア — mem0(Qdrant)→ Foundry Memory(プレビュー)の 1:1 置換。

元アプリ(mem0 0.1.29):

- ``memory.search(query=prompt, user_id=user_id)`` — 意味検索で関連記憶を取得
- ``memory.add(text, user_id=user_id, metadata={"role": ...})`` — 発言から
  LLM が事実を抽出して保存(user / assistant の発言を毎ターン 2 回)
- ``memory.get_all(user_id=user_id)`` — サイドバー「View My Memory」

移植後は Foundry Agent Service の Memory ストア API(azure-ai-projects
``client.beta.memory_stores``)。mem0 の ``user_id`` は Foundry の ``scope``
に 1:1 対応する(低レベル API では毎リクエスト明示必須)。

オフラインテスト要件(PORTING.md §4)のため、チャットループは
:class:`MemoryStore` protocol にのみ依存し、実装は 2 つ:

- :class:`FoundryMemoryStore` — 実 API(ライブ専用)。SDK が LRO ポーリング
  とプレビュー opt-in ヘッダー(``Foundry-Features``)を処理する
- :class:`InMemoryFakeStore` — オフラインテスト用のインプロセス実装
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from .config import TravelMemorySettings

#: search の既定取得件数(公式 how-to の ``max_memories=5`` に合わせる。
#: mem0 の search 既定 limit=100 は「全部注入」に近く、上限を明示する方針に変更)
DEFAULT_MAX_MEMORIES = 5


@dataclass
class MemoryRecord:
    """検索・一覧で得た記憶 1 件(mem0 の ``{"memory": ...}`` 相当)。

    kind は Foundry では user_profile / chat_summary / procedural の 3 種。
    フェイクでは追加時の role をそのまま入れる(テストの検証用)。
    """

    content: str
    kind: str = ""
    memory_id: str = ""


class MemoryStore(Protocol):
    """チャットループが必要とする最小面。テストではフェイクが置き換える。"""

    async def search(
        self, query: str, user_id: str, limit: int = DEFAULT_MAX_MEMORIES
    ) -> list[MemoryRecord]: ...

    async def add(self, text: str, user_id: str, role: str = "user") -> None: ...

    async def get_all(self, user_id: str) -> list[MemoryRecord]: ...


def _message_item(role: str, text: str) -> dict[str, str]:
    """Memory API の会話アイテム形式(Responses API の message item)。"""
    return {"role": role, "type": "message", "content": text}


def _to_record(item: Any) -> MemoryRecord:
    return MemoryRecord(
        content=str(getattr(item, "content", "") or ""),
        kind=str(getattr(item, "kind", "") or ""),
        memory_id=str(getattr(item, "memory_id", "") or ""),
    )


class FoundryMemoryStore:
    """Foundry Memory ストアの実接続(azure-ai-projects >= 2.3)。

    mem0 → Foundry の対応(詳細は README の対応表):

    - ``search`` → ``search_memories(name, scope, items=[質問], options)``
    - ``add``    → ``begin_update_memories(name, scope, items, previous_update_id,
      update_delay)``。**LRO(非同期の抽出・統合)** であり mem0 の同期 add と
      異なる。既定 ``update_delay=0`` で即時抽出をトリガーし、scope ごとに
      ``previous_update_id`` をチェーンして「毎ターン追加」を再現する。
      既定は fire-and-forget(``wait_for_update=True`` で完了まで待つ —
      ライブスモーク用)
    - ``get_all`` → ``list_memories(name, scope)``

    テストでは SDK クライアント互換のスタブを ``project_client`` に注入する。
    """

    def __init__(
        self,
        project_client: Any,
        store_name: str,
        *,
        update_delay: int = 0,
        wait_for_update: bool = False,
        credential: Any | None = None,
    ) -> None:
        self._client = project_client
        self._store_name = store_name
        self._update_delay = update_delay
        self._wait_for_update = wait_for_update
        self._credential = credential  # ファクトリ生成時のみ所有(aclose で閉じる)
        self._previous_update_ids: dict[str, str] = {}

    async def search(
        self, query: str, user_id: str, limit: int = DEFAULT_MAX_MEMORIES
    ) -> list[MemoryRecord]:
        from azure.ai.projects.models import MemorySearchOptions

        result = await self._client.beta.memory_stores.search_memories(
            name=self._store_name,
            scope=user_id,
            items=[_message_item("user", query)],
            options=MemorySearchOptions(max_memories=limit),
        )
        return [_to_record(memory.memory_item) for memory in result.memories]

    async def add(self, text: str, user_id: str, role: str = "user") -> None:
        poller = await self._client.beta.memory_stores.begin_update_memories(
            name=self._store_name,
            scope=user_id,
            items=[_message_item(role, text)],
            previous_update_id=self._previous_update_ids.get(user_id),
            update_delay=self._update_delay,
        )
        self._previous_update_ids[user_id] = poller.update_id
        if self._wait_for_update:
            await poller.result()

    async def get_all(self, user_id: str) -> list[MemoryRecord]:
        pages = self._client.beta.memory_stores.list_memories(
            name=self._store_name, scope=user_id
        )
        return [_to_record(item) async for item in pages]

    async def delete_all(self, user_id: str) -> None:
        """mem0 の ``delete_all(user_id=...)`` 相当 — scope 単位の全削除
        (``delete_scope``)。ライブスモークのテスト scope 掃除にも使う。"""
        await self._client.beta.memory_stores.delete_scope(
            name=self._store_name, scope=user_id
        )
        self._previous_update_ids.pop(user_id, None)

    async def aclose(self) -> None:
        await self._client.close()
        if self._credential is not None:
            await self._credential.close()


def make_foundry_memory_store(
    settings: TravelMemorySettings,
    *,
    update_delay: int = 0,
    wait_for_update: bool = False,
) -> FoundryMemoryStore:
    """実接続のストアを組み立てる(CLI / ライブスモーク用)。

    Memory API の認証は Entra ID のみ(API キー不可)。``az login`` 済みの
    環境で ``DefaultAzureCredential`` がトークンを取る。呼び出し側が
    ``aclose()`` すること。
    """
    from azure.ai.projects.aio import AIProjectClient
    from azure.identity.aio import DefaultAzureCredential

    credential = DefaultAzureCredential()
    client = AIProjectClient(endpoint=settings.project_endpoint, credential=credential)
    return FoundryMemoryStore(
        client,
        settings.memory_store,
        update_delay=update_delay,
        wait_for_update=wait_for_update,
        credential=credential,
    )


class InMemoryFakeStore:
    """オフラインテスト用のフェイク(mem0 の意味論の最小近似)。

    - ``add``: 発言をそのまま 1 記憶として保存(実サービスの LLM 事実抽出・
      統合は行わない)。kind に role を記録する
    - ``search``: 小文字化した内容語(3 文字以上・ストップワード除外)の
      集合の重なりでスコアリングし、重なり 0 を除外して上位 ``limit`` 件
      (意味検索の scripted 近似。同点は追加順)
    - ``user_id`` ごとに完全分離(Foundry の scope 分離に対応)
    """

    def __init__(self) -> None:
        self._records: dict[str, list[MemoryRecord]] = {}
        self._counter = 0

    async def add(self, text: str, user_id: str, role: str = "user") -> None:
        self._counter += 1
        self._records.setdefault(user_id, []).append(
            MemoryRecord(content=text, kind=role, memory_id=f"mem_{self._counter}")
        )

    async def search(
        self, query: str, user_id: str, limit: int = DEFAULT_MAX_MEMORIES
    ) -> list[MemoryRecord]:
        query_tokens = _tokens(query)
        scored: list[tuple[int, MemoryRecord]] = []
        for record in self._records.get(user_id, []):
            score = len(query_tokens & _tokens(record.content))
            if score > 0:
                scored.append((score, record))
        scored.sort(key=lambda pair: pair[0], reverse=True)  # 安定ソート: 同点は追加順
        return [record for _, record in scored[: max(0, limit)]]

    async def get_all(self, user_id: str) -> list[MemoryRecord]:
        return list(self._records.get(user_id, []))

    async def delete_all(self, user_id: str) -> None:
        self._records.pop(user_id, None)


#: 機能語での偽ヒットを避ける最小ストップワード(フェイクの検索は内容語のみ見る)
_STOPWORDS = frozenset(
    {"the", "and", "for", "with", "are", "was", "you", "your", "have", "has", "that", "this"}
)


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"\w+", text.lower())
        if len(token) >= 3 and token not in _STOPWORDS
    }

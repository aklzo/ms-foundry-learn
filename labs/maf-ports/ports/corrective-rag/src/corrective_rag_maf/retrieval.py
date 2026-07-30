"""ベクトル検索(Azure AI Search)— 元アプリの Qdrant retriever の置き換え。

元アプリ: LangChain の ``Qdrant(...).as_retriever()``(コサイン距離・
OpenAIEmbeddings text-embedding-3-small・k=4 既定)。

移植後: Azure AI Search の純ベクトル検索(HNSW・1536 次元)+クライアント側
埋め込み(integrated vectorization なし。設計判断は README)。

オフラインテスト要件(PORTING.md §4)のため、azure-search-documents への
依存は :class:`AzureSearchClientAdapter` に閉じ込め、ワークフローは
:class:`SupportsRetrieve`、リトリーバは :class:`SupportsVectorSearch` /
:class:`SupportsEmbed` の protocol にのみ依存する。テストでは fake を注入し、
実接続(azure-search-documents / openai)はライブスモークのみ。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .config import CorrectiveRagSettings

#: LangChain ``as_retriever()`` の既定 k を踏襲
DEFAULT_TOP_K = 4

#: text-embedding-3-small の次元数(scripts/setup_index.py のフィールド定義と一致)
EMBEDDING_DIMENSIONS = 1536

#: setup_index.py が作るベクトルフィールド名
VECTOR_FIELD = "content_vector"


@dataclass
class RetrievedDocument:
    """検索で得た文書チャンク(元アプリの langchain ``Document`` 相当)。"""

    content: str
    source: str = "Unknown"
    title: str = ""
    score: float | None = None


class SupportsRetrieve(Protocol):
    """ワークフローが必要とする最小面。テストでは fake が置き換える。"""

    async def retrieve(self, question: str) -> list[RetrievedDocument]: ...


class SupportsEmbed(Protocol):
    async def embed(self, text: str) -> list[float]: ...


class SupportsVectorSearch(Protocol):
    """インデックスへの純ベクトル検索。実装は AzureSearchClientAdapter(実接続)
    またはテストの fake。戻り値は AI Search の検索結果ドキュメント(dict)。"""

    async def search(self, vector: list[float], top: int) -> list[dict[str, Any]]: ...


class AzureSearchRetriever:
    """質問 → クライアント側埋め込み → ベクトル検索 → RetrievedDocument。"""

    def __init__(
        self,
        searcher: SupportsVectorSearch,
        embedder: SupportsEmbed,
        top_k: int = DEFAULT_TOP_K,
    ) -> None:
        self._searcher = searcher
        self._embedder = embedder
        self._top_k = max(1, top_k)

    async def retrieve(self, question: str) -> list[RetrievedDocument]:
        vector = await self._embedder.embed(question)
        rows = await self._searcher.search(vector, self._top_k)
        return [
            RetrievedDocument(
                content=str(row.get("content", "")),
                source=str(row.get("source", "Unknown")),
                title=str(row.get("title", "")),
                score=row.get("@search.score"),
            )
            for row in rows
        ]


class OpenAIEmbedder:
    """Foundry の OpenAI v1 エンドポイント経由のクライアント側埋め込み。

    元アプリの ``OpenAIEmbeddings(model="text-embedding-3-small")`` に対応。
    openai パッケージはライブ実行時のみ必要(lazy import)。
    """

    def __init__(self, settings: CorrectiveRagSettings) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(
            base_url=settings.openai_v1_endpoint, api_key=settings.api_key
        )
        self._model = settings.embedding_model

    async def embed(self, text: str) -> list[float]:
        response = await self._client.embeddings.create(model=self._model, input=[text])
        return list(response.data[0].embedding)


class AzureSearchClientAdapter:
    """azure-search-documents(async SearchClient)の薄いアダプタ。

    実接続はここに閉じる(ライブスモーク/CLI のみ)。インデックスは
    scripts/setup_index.py で事前作成しておくこと。
    """

    def __init__(self, settings: CorrectiveRagSettings) -> None:
        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents.aio import SearchClient

        self._client = SearchClient(
            endpoint=settings.search_endpoint,
            index_name=settings.search_index,
            credential=AzureKeyCredential(settings.search_api_key),
        )

    async def search(self, vector: list[float], top: int) -> list[dict[str, Any]]:
        from azure.search.documents.models import VectorizedQuery

        # 元アプリ同様の純ベクトル検索(search_text=None)。ハイブリッドにする
        # 場合は search_text に質問文を渡すだけでよい(README の学び参照)。
        results = await self._client.search(
            search_text=None,
            vector_queries=[
                VectorizedQuery(vector=vector, k_nearest_neighbors=top, fields=VECTOR_FIELD)
            ],
            select=["content", "source", "title"],
            top=top,
        )
        return [dict(row) async for row in results]

    async def aclose(self) -> None:
        await self._client.close()


def make_azure_search_retriever(
    settings: CorrectiveRagSettings, top_k: int = DEFAULT_TOP_K
) -> tuple[AzureSearchRetriever, AzureSearchClientAdapter]:
    """実接続のリトリーバを組み立てる(CLI / ライブスモーク用)。

    戻り値の adapter は呼び出し側が ``aclose()`` すること。
    """
    adapter = AzureSearchClientAdapter(settings)
    return AzureSearchRetriever(adapter, OpenAIEmbedder(settings), top_k=top_k), adapter

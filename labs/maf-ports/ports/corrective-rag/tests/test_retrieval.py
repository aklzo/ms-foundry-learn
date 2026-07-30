"""リトリーバのオフラインテスト。

PORTING.md §4 に従い、azure-search-documents への実接続はライブスモークに
限定し、ここでは protocol(SupportsVectorSearch / SupportsEmbed)への fake
注入で AzureSearchRetriever のマッピングロジックだけを検証する。
"""

from typing import Any

from corrective_rag_maf.retrieval import DEFAULT_TOP_K, AzureSearchRetriever


class FakeEmbedder:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def embed(self, text: str) -> list[float]:
        self.texts.append(text)
        return [0.1, 0.2, 0.3]


class FakeSearcher:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[tuple[list[float], int]] = []

    async def search(self, vector: list[float], top: int) -> list[dict[str, Any]]:
        self.calls.append((vector, top))
        return self.rows


async def test_retriever_embeds_question_and_maps_rows() -> None:
    searcher = FakeSearcher(
        [
            {
                "content": "Free tier: 3 indexes, 50MB storage.",
                "source": "azure-ai-search-vector-tiers.md",
                "title": "Azure AI Search",
                "@search.score": 0.83,
            },
            {"content": "chunk without metadata"},
        ]
    )
    embedder = FakeEmbedder()
    retriever = AzureSearchRetriever(searcher, embedder)

    docs = await retriever.retrieve("What are the free tier limits?")

    assert embedder.texts == ["What are the free tier limits?"]
    assert searcher.calls == [([0.1, 0.2, 0.3], DEFAULT_TOP_K)]

    assert docs[0].content == "Free tier: 3 indexes, 50MB storage."
    assert docs[0].source == "azure-ai-search-vector-tiers.md"
    assert docs[0].title == "Azure AI Search"
    assert docs[0].score == 0.83
    # メタデータ欠落は既定値に落ちる(元 langchain Document の metadata.get 相当)
    assert docs[1].source == "Unknown"
    assert docs[1].title == ""
    assert docs[1].score is None


async def test_retriever_respects_top_k_and_clamps_to_one() -> None:
    searcher = FakeSearcher([])
    retriever = AzureSearchRetriever(searcher, FakeEmbedder(), top_k=7)
    await retriever.retrieve("q")
    assert searcher.calls[0][1] == 7

    clamped = AzureSearchRetriever(FakeSearcher([]), FakeEmbedder(), top_k=0)
    assert clamped._top_k == 1  # 内部値の下限クランプ確認


async def test_retriever_returns_empty_for_no_rows() -> None:
    retriever = AzureSearchRetriever(FakeSearcher([]), FakeEmbedder())
    assert await retriever.retrieve("q") == []

"""AI Search ハイブリッドインデックス(BM25 ja.lucene + ベクトル)。

- 本文は ja.lucene アナライザー(日本語形態素)。ベクトルは text-embedding-3-small
  (1536 次元)を HNSW で検索。ハイブリッド = 両方を投げて RRF 統合(サービス既定)
- 埋め込みはアカウントエンドポイント経由(foundry-probes 08 の実測: プロジェクト
  経由の embeddings は 404。本ラボは最初からアカウント直)
"""

from __future__ import annotations

import httpx
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    ScoringProfile,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SimpleField,
    TextWeights,
    VectorSearch,
    VectorSearchProfile,
)
from azure.search.documents.models import VectorizedQuery

EMBED_DIM = 1536


class Embedder:
    def __init__(self, aoai_endpoint: str, key: str, deployment: str = "text-embedding-3-small"):
        self.url = (
            f"{aoai_endpoint.rstrip('/')}/openai/deployments/{deployment}"
            "/embeddings?api-version=2024-10-21"
        )
        self.http = httpx.Client(headers={"api-key": key}, timeout=60)

    def embed(self, texts: list[str]) -> list[list[float]]:
        r = self.http.post(self.url, json={"input": texts})
        r.raise_for_status()
        return [d["embedding"] for d in r.json()["data"]]


def build_index(index_client: SearchIndexClient, name: str) -> None:
    index = SearchIndex(
        name=name,
        fields=[
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SimpleField(name="video_id", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="start_s", type=SearchFieldDataType.Double, filterable=True),
            SimpleField(name="end_s", type=SearchFieldDataType.Double, filterable=True),
            SearchableField(name="content", type=SearchFieldDataType.String, analyzer_name="ja.lucene"),
            SearchableField(name="screen_texts", type=SearchFieldDataType.String, analyzer_name="ja.lucene"),
            SearchField(
                name="content_vector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=EMBED_DIM,
                vector_search_profile_name="hnsw",
            ),
        ],
        vector_search=VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="hnsw-algo")],
            profiles=[VectorSearchProfile(name="hnsw", algorithm_configuration_name="hnsw-algo")],
        ),
        # 構成 D 用: 画面内テキストの一致を本文より強く効かせる(BM25 側の重みのみ)
        scoring_profiles=[
            ScoringProfile(
                name="boost-screen",
                text_weights=TextWeights(weights={"content": 1.0, "screen_texts": 2.0}),
            )
        ],
    )
    index_client.create_or_update_index(index)


def upload_chunks(
    endpoint: str, admin_key: str, index_name: str, chunks: list[dict], embedder: Embedder
) -> int:
    index_client = SearchIndexClient(endpoint, AzureKeyCredential(admin_key))
    build_index(index_client, index_name)
    # ベクトルは本文+画面内テキストを合わせて埋め込む(分離してもベクトル再現率は保つ)
    vectors = embedder.embed(
        [f"{c['content']}\n{c['screen_texts']}".strip() for c in chunks]
    )
    docs = [{**c, "content_vector": v} for c, v in zip(chunks, vectors)]
    client = SearchClient(endpoint, index_name, AzureKeyCredential(admin_key))
    result = client.upload_documents(docs)
    return sum(1 for r in result if r.succeeded)


def hybrid_search(
    endpoint: str,
    admin_key: str,
    index_name: str,
    query: str,
    embedder: Embedder,
    top: int = 5,
    scoring_profile: str | None = None,
) -> list[dict]:
    client = SearchClient(endpoint, index_name, AzureKeyCredential(admin_key))
    vq = VectorizedQuery(vector=embedder.embed([query])[0], fields="content_vector", k_nearest_neighbors=top)
    results = client.search(
        search_text=query, vector_queries=[vq], top=top, scoring_profile=scoring_profile
    )
    return [
        {
            "id": r["id"],
            "video_id": r["video_id"],
            "start_s": r["start_s"],
            "end_s": r["end_s"],
            "score": r["@search.score"],
            # 回答含有判定は「取得ドキュメント全体」に対して行う(screen_texts も RAG に渡る)
            "content": "\n".join(filter(None, [r["content"], r.get("screen_texts") or ""])),
        }
        for r in results
    ]

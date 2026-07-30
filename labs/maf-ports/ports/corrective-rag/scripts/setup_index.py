"""Azure AI Search のインデックス作成+サンプル文書投入(ライブ専用)。

元アプリの「Streamlit 上で文書 URL/アップロード → tiktoken ベースの
チャンク分割 → Qdrant コレクション作成 → 投入」に対応する事前バッチ。
インデックス構成はクライアント側埋め込み前提(integrated vectorization
なし。設計判断は README):

- フィールド: id(キー)/ content / source / title / content_vector
  (1536 次元・HNSW プロファイル)
- 埋め込み: Foundry の OpenAI v1 エンドポイント経由で text-embedding-3-small
  (infra/main.bicep が共有 Foundry アカウントにデプロイを追加する)
- 文書: data/*.md(Foundry ドキュメントのラボ用要約)を段落単位で
  チャンク化(元の RecursiveCharacterTextSplitter 500 トークン/100 重複の
  近似。tiktoken 依存を避け文字数基準にした)

実行(要 `uv sync --extra live` + labs/maf-ports/.env):

    uv run python scripts/setup_index.py
    uv run python scripts/setup_index.py --recreate   # 元アプリ同様に作り直す

冪等: 既定は create_or_update + 同一キーの upsert。--recreate で元アプリの
「delete_collection → create_collection」を再現する。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PORT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PORT_ROOT / "data"
sys.path.insert(0, str(PORT_ROOT / "src"))

from corrective_rag_maf.config import CorrectiveRagSettings
from corrective_rag_maf.retrieval import EMBEDDING_DIMENSIONS, VECTOR_FIELD

#: 元の RecursiveCharacterTextSplitter(chunk_size=500 tokens, overlap=100)の
#: 文字数近似(日本語主体のコーパスなので 1 トークン≒1.5 文字で概算)
CHUNK_MAX_CHARS = 800
CHUNK_OVERLAP_CHARS = 150


def chunk_markdown(text: str) -> list[str]:
    """段落境界を優先した貪欲チャンク分割(＋文字数上限・末尾重複)。"""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= CHUNK_MAX_CHARS:
            current = candidate
            continue
        if current:
            chunks.append(current)
            # 元 splitter の chunk_overlap 相当: 直前チャンク末尾を持ち越す
            current = current[-CHUNK_OVERLAP_CHARS:] + "\n\n" + paragraph
        else:
            current = paragraph
        while len(current) > CHUNK_MAX_CHARS:
            chunks.append(current[:CHUNK_MAX_CHARS])
            current = current[CHUNK_MAX_CHARS - CHUNK_OVERLAP_CHARS :]
    if current:
        chunks.append(current)
    return chunks


def build_index_definition(index_name: str):
    from azure.search.documents.indexes.models import (
        HnswAlgorithmConfiguration,
        SearchableField,
        SearchField,
        SearchFieldDataType,
        SearchIndex,
        SimpleField,
        VectorSearch,
        VectorSearchProfile,
    )

    return SearchIndex(
        name=index_name,
        fields=[
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SearchableField(name="content", type=SearchFieldDataType.String),
            SimpleField(name="source", type=SearchFieldDataType.String, filterable=True),
            SearchableField(name="title", type=SearchFieldDataType.String),
            SearchField(
                name=VECTOR_FIELD,
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=EMBEDDING_DIMENSIONS,
                vector_search_profile_name="hnsw-profile",
            ),
        ],
        vector_search=VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="hnsw")],
            profiles=[
                VectorSearchProfile(name="hnsw-profile", algorithm_configuration_name="hnsw")
            ],
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="corrective-rag インデックス作成+文書投入")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="既存インデックスを削除してから作り直す(元アプリの delete→create 相当)",
    )
    args = parser.parse_args()

    settings = CorrectiveRagSettings.from_env()

    from azure.core.credentials import AzureKeyCredential
    from azure.core.exceptions import ResourceNotFoundError
    from azure.search.documents import SearchClient
    from azure.search.documents.indexes import SearchIndexClient
    from openai import OpenAI

    credential = AzureKeyCredential(settings.search_api_key)
    index_client = SearchIndexClient(endpoint=settings.search_endpoint, credential=credential)

    if args.recreate:
        try:
            index_client.delete_index(settings.search_index)
            print(f"deleted index: {settings.search_index}")
        except ResourceNotFoundError:
            print("no existing index to delete")  # 元アプリ同様、存在しなければ無視

    index_client.create_or_update_index(build_index_definition(settings.search_index))
    print(f"index ready: {settings.search_index} ({settings.search_endpoint})")

    # --- チャンク化 ---
    files = sorted(DATA_DIR.glob("*.md"))
    if not files:
        print(f"error: no .md files in {DATA_DIR}", file=sys.stderr)
        sys.exit(1)
    documents: list[dict] = []
    for path in files:
        for i, chunk in enumerate(chunk_markdown(path.read_text(encoding="utf-8"))):
            title = chunk.splitlines()[0].lstrip("# ").strip()
            documents.append(
                {
                    "id": f"{path.stem}-{i:03d}",
                    "content": chunk,
                    "source": path.name,
                    "title": title,
                }
            )
    print(f"chunked {len(files)} files into {len(documents)} chunks")

    # --- クライアント側埋め込み(text-embedding-3-small @ Foundry)---
    openai_client = OpenAI(base_url=settings.openai_v1_endpoint, api_key=settings.api_key)
    batch_size = 16
    for start in range(0, len(documents), batch_size):
        batch = documents[start : start + batch_size]
        response = openai_client.embeddings.create(
            model=settings.embedding_model,
            input=[doc["content"] for doc in batch],
        )
        for doc, item in zip(batch, response.data, strict=True):
            doc[VECTOR_FIELD] = item.embedding
    print(f"embedded with {settings.embedding_model}")

    # --- 投入(同一キーは上書き = 冪等)---
    search_client = SearchClient(
        endpoint=settings.search_endpoint,
        index_name=settings.search_index,
        credential=credential,
    )
    result = search_client.merge_or_upload_documents(documents)
    succeeded = sum(1 for r in result if r.succeeded)
    print(f"uploaded {succeeded}/{len(documents)} chunks")
    if succeeded != len(documents):
        sys.exit(1)


if __name__ == "__main__":
    main()

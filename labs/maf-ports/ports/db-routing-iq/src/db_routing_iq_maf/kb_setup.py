"""Foundry IQ knowledge base のペイロード組み立て(純関数)。

元アプリの Qdrant ×3 コレクション+三段カスケードルーティングのうち、
「どのソースへ振り分けるか」をサービス側(agentic retrieval)に移すための
オブジェクト群を定義する:

- 検索インデックス ×3(products / support / finance — 元 COLLECTIONS と 1:1)
- searchIndex knowledge source ×3(インデックスを包む。description が
  LLM のソース選択材料になる)
- knowledge base ×1(3 ソースを束ね、retrievalReasoningEffort=low で
  LLM クエリプランニング=ルーティングを有効化。retrievalInstructions は
  元アプリの agno ルーティングエージェントの指示 1〜3 を移植)

すべて REST ペイロード(dict)を返す純関数で、ネットワークは触らない。
実際の PUT / 文書投入は scripts/setup_kb.py(ライブ専用)が行う。
azure-search-documents SDK は使わない — knowledge base 系は
2026-05-01-preview の preview SDK(--pre)が必要になるため、REST +
httpx で API 面を直接扱う(設計判断は README)。

インデックスにベクトルフィールドは持たせない(テキスト+セマンティック
ランカー L2 のみ。設計判断は README)。semantic configuration は agentic
retrieval の必須要件(prioritizedContentFields が必要)。
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import SEARCH_API_VERSION

__all__ = [
    "CHUNK_MAX_CHARS",
    "CHUNK_OVERLAP_CHARS",
    "DOMAINS",
    "SEARCH_API_VERSION",
    "SEMANTIC_CONFIG_NAME",
    "DomainConfig",
    "build_documents",
    "build_index_payload",
    "build_knowledge_base_payload",
    "build_knowledge_source_payload",
    "chunk_markdown",
]

#: 全インデックス共通のセマンティック構成名(agentic retrieval の必須要件)
SEMANTIC_CONFIG_NAME = "kb-semantic"

#: 元の RecursiveCharacterTextSplitter(chunk_size=1000, overlap=200)の
#: 文字数近似(corrective-rag の chunk_markdown と同じ規約。日本語主体の
#: コーパスなので控えめに 800/150)
CHUNK_MAX_CHARS = 800
CHUNK_OVERLAP_CHARS = 150


@dataclass(frozen=True)
class DomainConfig:
    """元アプリの CollectionConfig に対応(collection_name → index/KS 名)。"""

    domain: str  # 元の DatabaseType("products" | "support" | "finance")
    display_name: str  # 元の CollectionConfig.name
    description: str  # 元の CollectionConfig.description + ルーティング規則
    index_name: str
    knowledge_source_name: str


#: 元 COLLECTIONS と 1:1。description は元の CollectionConfig.description に、
#: 元ルーティングエージェントの規則(instructions 1〜3)の語彙を足したもの。
#: LLM ソース選択(low reasoning effort)はこの description を材料にする。
DOMAINS: tuple[DomainConfig, ...] = (
    DomainConfig(
        domain="products",
        display_name="Product Information",
        description=(
            "Product details, specifications, and features. Use for questions about "
            "products, features, specifications, item details, or product manuals."
        ),
        index_name="db-routing-products",
        knowledge_source_name="db-routing-products-ks",
    ),
    DomainConfig(
        domain="support",
        display_name="Customer Support & FAQ",
        description=(
            "Customer support information, frequently asked questions, and guides. "
            "Use for questions about help, guidance, troubleshooting, customer "
            "service, FAQ, or how-to guides."
        ),
        index_name="db-routing-support",
        knowledge_source_name="db-routing-support-ks",
    ),
    DomainConfig(
        domain="finance",
        display_name="Financial Information",
        description=(
            "Financial data, revenue, costs, and liabilities. Use for questions "
            "about costs, revenue, pricing, financial data, financial reports, or "
            "investments."
        ),
        index_name="db-routing-finance",
        knowledge_source_name="db-routing-finance-ks",
    ),
)

#: 元アプリの create_routing_agent の instructions 1〜3 を knowledge base の
#: retrievalInstructions へ移植したもの。元は「LLM がコレクション名を 1 語
#: 返す」ためのプロンプトだったが、移植後は「LLM がソースを選んで副クエリを
#: 出す」ためのガイドになる(消費者がアプリから検索サービスへ移る)。
RETRIEVAL_INSTRUCTIONS = (
    "Route each question to the most relevant knowledge source(s): "
    "questions about products, features, specifications, item details, or product "
    "manuals belong to the products source; questions about help, guidance, "
    "troubleshooting, customer service, FAQ, or guides belong to the support "
    "source; questions about costs, revenue, pricing, financial data, financial "
    "reports, or investments belong to the finance source. Skip sources that are "
    "clearly unrelated to the question."
)


def chunk_markdown(text: str) -> list[str]:
    """段落境界を優先した貪欲チャンク分割(+文字数上限・末尾重複)。

    corrective-rag の scripts/setup_index.py と同一規約(元アプリの
    RecursiveCharacterTextSplitter 1000/200 の近似)。
    """
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


def build_index_payload(config: DomainConfig) -> dict:
    """インデックス定義(REST PUT /indexes/{name} のボディ)。

    agentic retrieval の必須要件(searchable+retrievable な文字列フィールド、
    semantic configuration)を満たす最小構成。``description`` は LLM ソース
    選択の材料(インデックス説明もプランナに渡る)。ベクトルフィールドは
    持たない(設計判断は README)。
    """
    return {
        "name": config.index_name,
        "description": f"{config.display_name}: {config.description}",
        "fields": [
            {"name": "id", "type": "Edm.String", "key": True, "filterable": True},
            {"name": "content", "type": "Edm.String", "searchable": True, "retrievable": True},
            {"name": "title", "type": "Edm.String", "searchable": True, "retrievable": True},
            {"name": "source", "type": "Edm.String", "filterable": True, "retrievable": True},
            {"name": "domain", "type": "Edm.String", "filterable": True, "retrievable": True},
        ],
        "semantic": {
            "defaultConfiguration": SEMANTIC_CONFIG_NAME,
            "configurations": [
                {
                    "name": SEMANTIC_CONFIG_NAME,
                    "prioritizedFields": {
                        "titleField": {"fieldName": "title"},
                        "prioritizedContentFields": [{"fieldName": "content"}],
                        "prioritizedKeywordsFields": [],
                    },
                }
            ],
        },
    }


def build_documents(config: DomainConfig, files: dict[str, str]) -> list[dict]:
    """data/<domain>/*.md → 投入ドキュメント列(チャンク化+メタデータ付与)。

    ``files`` は {ファイル名(拡張子なし): 本文}。id は冪等な連番キー、
    title は先頭行(見出し)、``domain`` はルーティング検証用のメタデータ
    (retrieve 応答の sourceData に現れる)。
    """
    documents: list[dict] = []
    for stem in sorted(files):
        text = files[stem]
        for i, chunk in enumerate(chunk_markdown(text)):
            title = chunk.splitlines()[0].lstrip("# ").strip()
            documents.append(
                {
                    "id": f"{config.domain}-{stem}-{i:03d}",
                    "content": chunk,
                    "title": title,
                    "source": f"{stem}.md",
                    "domain": config.domain,
                }
            )
    return documents


def build_knowledge_source_payload(config: DomainConfig) -> dict:
    """searchIndex knowledge source 定義(REST PUT /knowledgesources/{name})。

    既存インデックスを包む「bring your own index」形。sourceDataFields で
    retrieve 応答に含めるフィールドを指定する(domain を含めることで、
    どのソースから引いたかを応答側で検証できる)。semanticConfigurationName
    は 2026-05-01-preview では省略可だが、インデックス側の
    defaultSemanticConfiguration を明示的に指す。
    """
    return {
        "name": config.knowledge_source_name,
        "kind": "searchIndex",
        "description": f"{config.display_name}: {config.description}",
        "searchIndexParameters": {
            "searchIndexName": config.index_name,
            "semanticConfigurationName": SEMANTIC_CONFIG_NAME,
            "sourceDataFields": [
                {"name": "id"},
                {"name": "title"},
                {"name": "source"},
                {"name": "domain"},
            ],
        },
    }


def build_knowledge_base_payload(
    kb_name: str,
    *,
    aoai_resource_uri: str,
    aoai_api_key: str,
    model_deployment: str,
) -> dict:
    """knowledge base 定義(REST PUT /knowledgebases/{name})。

    - knowledgeSources: 3 ドメインの KS を束ねる(元アプリの「全 DB を検索して
      比較」に相当する fan-out はサービス側が行う)
    - models + retrievalReasoningEffort=low: LLM クエリプランニング=
      サービス側ルーティングを有効化(元アプリの閾値判定+LLM ルートの置換)。
      認証はキー(ラボ規約。MI 経路は Basic 以上限定+ロール割当が必要)
    - outputMode は未指定(既定の抽出的グラウンディング)。回答統合は
      MAF エージェント側で行う — 元アプリの retrieval chain の位置に合わせる
      (answerSynthesis にしない判断は README)
    """
    return {
        "name": kb_name,
        "description": (
            "Company knowledge routed across product information, customer support "
            "/ FAQ, and financial information sources."
        ),
        "retrievalInstructions": RETRIEVAL_INSTRUCTIONS,
        "knowledgeSources": [
            {"name": config.knowledge_source_name} for config in DOMAINS
        ],
        "models": [
            {
                "kind": "azureOpenAI",
                "azureOpenAIParameters": {
                    "resourceUri": aoai_resource_uri,
                    "apiKey": aoai_api_key,
                    "deploymentId": model_deployment,
                    "modelName": model_deployment,
                },
            }
        ],
        "retrievalReasoningEffort": {"kind": "low"},
    }

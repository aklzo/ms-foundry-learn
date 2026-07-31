"""knowledge base セットアップのペイロード組み立て(純関数)のオフラインテスト。

scripts/setup_kb.py が PUT する JSON の形をここで固定する(実 PUT はライブ
のみ)。ペイロードの形は Learn の REST リファレンス(2026-05-01-preview)の
例に基づく(README の実装前調査参照)。
"""

from db_routing_iq_maf.kb_setup import (
    CHUNK_MAX_CHARS,
    CHUNK_OVERLAP_CHARS,
    DOMAINS,
    SEMANTIC_CONFIG_NAME,
    build_documents,
    build_index_payload,
    build_knowledge_base_payload,
    build_knowledge_source_payload,
    chunk_markdown,
)

PRODUCTS = DOMAINS[0]


# --- ドメイン構成(元アプリの COLLECTIONS と 1:1)---


def test_domains_mirror_original_collections() -> None:
    assert [config.domain for config in DOMAINS] == ["products", "support", "finance"]
    assert [config.display_name for config in DOMAINS] == [
        "Product Information",
        "Customer Support & FAQ",
        "Financial Information",
    ]


def test_domain_object_names_are_distinct_and_prefixed() -> None:
    index_names = {config.index_name for config in DOMAINS}
    ks_names = {config.knowledge_source_name for config in DOMAINS}

    assert len(index_names) == len(ks_names) == 3
    assert all(name.startswith("db-routing-") for name in index_names | ks_names)


# --- チャンク分割(元の RecursiveCharacterTextSplitter 1000/200 の近似)---


def test_chunk_markdown_short_text_is_single_chunk() -> None:
    assert chunk_markdown("# Title\n\nshort body") == ["# Title\n\nshort body"]


def test_chunk_markdown_splits_long_text_with_overlap() -> None:
    paragraphs = [f"paragraph {i} " + ("x" * 300) for i in range(5)]
    chunks = chunk_markdown("\n\n".join(paragraphs))

    assert len(chunks) > 1
    assert all(len(chunk) <= CHUNK_MAX_CHARS for chunk in chunks)
    # 直前チャンク末尾の持ち越し(overlap)
    assert chunks[1].startswith(chunks[0][-CHUNK_OVERLAP_CHARS:])


def test_chunk_markdown_ignores_blank_paragraphs() -> None:
    assert chunk_markdown("a\n\n\n\n\n\nb") == ["a\n\nb"]


# --- インデックス定義 ---


def test_index_payload_meets_agentic_retrieval_criteria() -> None:
    payload = build_index_payload(PRODUCTS)

    assert payload["name"] == PRODUCTS.index_name
    # searchable + retrievable な文字列フィールド(必須要件)
    content = next(f for f in payload["fields"] if f["name"] == "content")
    assert content["searchable"] is True and content["retrievable"] is True
    # semantic configuration(必須要件): defaultConfiguration + content 優先
    assert payload["semantic"]["defaultConfiguration"] == SEMANTIC_CONFIG_NAME
    config = payload["semantic"]["configurations"][0]
    assert config["name"] == SEMANTIC_CONFIG_NAME
    assert config["prioritizedFields"]["prioritizedContentFields"] == [{"fieldName": "content"}]


def test_index_payload_has_no_vector_search() -> None:
    """設計判断: ベクトルなし(テキスト+L2 セマンティックリランクのみ)。"""
    payload = build_index_payload(PRODUCTS)

    assert "vectorSearch" not in payload
    assert all("dimensions" not in f for f in payload["fields"])


def test_index_payload_description_feeds_llm_source_selection() -> None:
    """インデックス description は LLM ソース選択の材料(実装前調査)。"""
    payload = build_index_payload(PRODUCTS)

    assert "Product Information" in payload["description"]
    assert "specifications" in payload["description"]


def test_index_key_field_is_id() -> None:
    payload = build_index_payload(PRODUCTS)

    key_fields = [f for f in payload["fields"] if f.get("key")]
    assert [f["name"] for f in key_fields] == ["id"]


# --- 文書の組み立て ---


def test_build_documents_ids_titles_and_domain_metadata() -> None:
    files = {
        "aurora-x10": "# Aurora X10 spec\n\nweighs 1.2kg",
        "breeze-s2": "# Breeze S2 spec\n\nquiet fan",
    }

    documents = build_documents(PRODUCTS, files)

    assert [doc["id"] for doc in documents] == [
        "products-aurora-x10-000",
        "products-breeze-s2-000",
    ]
    assert documents[0]["title"] == "Aurora X10 spec"
    assert documents[0]["source"] == "aurora-x10.md"
    assert all(doc["domain"] == "products" for doc in documents)


def test_build_documents_chunks_long_files() -> None:
    long_text = "# Long doc\n\n" + "\n\n".join("y" * 500 for _ in range(4))

    documents = build_documents(PRODUCTS, {"long": long_text})

    assert len(documents) > 1
    assert documents[1]["id"] == "products-long-001"


# --- knowledge source 定義 ---


def test_knowledge_source_payload_wraps_index() -> None:
    payload = build_knowledge_source_payload(PRODUCTS)

    assert payload["name"] == PRODUCTS.knowledge_source_name
    assert payload["kind"] == "searchIndex"
    params = payload["searchIndexParameters"]
    assert params["searchIndexName"] == PRODUCTS.index_name
    assert params["semanticConfigurationName"] == SEMANTIC_CONFIG_NAME


def test_knowledge_source_source_data_includes_domain() -> None:
    """retrieve 応答の sourceData に domain を含め、どのソースから引いたかを
    応答側で検証できるようにする。"""
    params = build_knowledge_source_payload(PRODUCTS)["searchIndexParameters"]

    assert {"name": "domain"} in params["sourceDataFields"]


def test_knowledge_source_description_carries_routing_vocabulary() -> None:
    payload = build_knowledge_source_payload(DOMAINS[1])

    assert "troubleshooting" in payload["description"]
    assert "FAQ" in payload["description"]


# --- knowledge base 定義 ---


def make_kb_payload() -> dict:
    return build_knowledge_base_payload(
        "db-routing-kb",
        aoai_resource_uri="https://aif-example.openai.azure.com",
        aoai_api_key="foundry-key",
        model_deployment="gpt-5.4-mini",
    )


def test_kb_payload_bundles_three_knowledge_sources() -> None:
    payload = make_kb_payload()

    assert payload["name"] == "db-routing-kb"
    assert payload["knowledgeSources"] == [
        {"name": "db-routing-products-ks"},
        {"name": "db-routing-support-ks"},
        {"name": "db-routing-finance-ks"},
    ]


def test_kb_payload_enables_llm_query_planning() -> None:
    """retrievalReasoningEffort=low + models = サービス側ルーティングの有効化
    (元アプリの閾値検索+LLM ルートの置換点)。"""
    payload = make_kb_payload()

    assert payload["retrievalReasoningEffort"] == {"kind": "low"}
    model = payload["models"][0]
    assert model["kind"] == "azureOpenAI"
    params = model["azureOpenAIParameters"]
    assert params["resourceUri"] == "https://aif-example.openai.azure.com"
    assert params["apiKey"] == "foundry-key"
    assert params["deploymentId"] == params["modelName"] == "gpt-5.4-mini"


def test_kb_payload_retrieval_instructions_port_original_routing_rules() -> None:
    """元アプリの agno ルーティングエージェント instructions 1〜3 の移植。"""
    instructions = make_kb_payload()["retrievalInstructions"]

    assert "products" in instructions
    assert "support" in instructions
    assert "finance" in instructions
    assert "troubleshooting" in instructions  # 規則 2 の語彙
    assert "revenue" in instructions  # 規則 3 の語彙


def test_kb_payload_leaves_answer_synthesis_to_the_agent() -> None:
    """outputMode は未指定(既定の抽出的グラウンディング)。回答統合は
    MAF エージェント側 — 元アプリの retrieval chain の位置(設計判断)。"""
    assert "outputMode" not in make_kb_payload()

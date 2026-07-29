from agentic_search_maf.knowledge import Finding, KnowledgeStore


def finding(statement: str, url: str) -> Finding:
    return Finding(statement=statement, source_url=url, source_title="title")


def test_deduplicates_equivalent_statements():
    store = KnowledgeStore()
    assert store.add_finding(finding("Rust 1.95 was released", "https://a.example"))
    assert not store.add_finding(finding("rust  1.95 WAS released", "https://b.example"))
    assert len(store.findings) == 1


def test_tracks_visited_urls_and_queries():
    store = KnowledgeStore()
    assert store.mark_visited("https://a.example")
    assert store.is_visited("https://a.example")
    assert store.mark_query("rust async runtime")
    assert not store.mark_query("Rust   ASYNC runtime")


def test_digest_lists_findings_with_sources():
    store = KnowledgeStore()
    store.add_finding(finding("Fact one", "https://a.example"))
    store.add_finding(finding("Fact two", "https://b.example"))
    digest = store.digest(500)
    assert "[1] Fact one" in digest
    assert "https://b.example" in digest
    assert store.source_count() == 2


def test_digest_respects_char_budget():
    store = KnowledgeStore()
    for index in range(50):
        store.add_finding(
            finding(f"A reasonably long statement number {index}", "https://a.example")
        )
    digest = store.digest(300)
    assert len(digest) < 400
    assert "truncated" in digest

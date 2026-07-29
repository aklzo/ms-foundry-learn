from agentic_search_maf.fetch.extract import html_to_text
from agentic_search_maf.search import parse_ddg_results

DDG_FIXTURE = """
<html><body>
  <div class="result">
    <a class="result__a"
       href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage&rut=abc">Example Title</a>
    <a class="result__snippet">An example snippet.</a>
  </div>
  <div class="result">
    <a class="result__a" href="https://direct.example.org/doc">Direct Link</a>
  </div>
  <div class="result"><span>no link here</span></div>
</body></html>"""


def test_parses_redirect_wrapped_and_direct_results():
    hits = parse_ddg_results(DDG_FIXTURE)
    assert len(hits) == 2
    assert hits[0].url == "https://example.com/page"
    assert hits[0].title == "Example Title"
    assert hits[0].snippet == "An example snippet."
    assert hits[1].url == "https://direct.example.org/doc"
    assert hits[1].snippet == ""


def test_empty_page_yields_no_hits():
    assert parse_ddg_results("<html><body></body></html>") == []


def test_extracts_visible_text_and_skips_scripts():
    html = """<html><head><title>T</title><style>p{color:red}</style></head>
        <body><h1>Heading</h1><script>var secret = 1;</script>
        <p>First   paragraph.</p><p>Second.</p></body></html>"""
    text = html_to_text(html, 1000)
    assert "Heading" in text
    assert "First paragraph." in text
    assert "secret" not in text
    assert "color" not in text


def test_truncates_by_char_count():
    html = "<body><p>日本語のテキストです</p></body>"
    assert html_to_text(html, 3) == "日本語"


def test_handles_documents_without_body():
    assert html_to_text("just plain text", 100) == "just plain text"


def test_readability_keeps_article_body():
    body = (
        "Tokio is an asynchronous runtime for the Rust programming language. "
        "It provides the building blocks needed for writing networking applications. "
        "The runtime includes a multi-threaded, work-stealing scheduler and an "
        "event-driven, non-blocking I/O reactor. Tasks are lightweight green threads "
        "that begin running immediately when spawned onto the runtime scheduler."
    )
    html = f"""<html><body>
        <nav><a href="/">Home</a><a href="/login">Sign in to your account</a></nav>
        <article><h1>The Tokio Runtime</h1><p>{body}</p><p>{body}</p></article>
        <footer>Copyright 2026 Example Corp. All rights reserved.</footer>
    </body></html>"""
    text = html_to_text(html, 5000)
    assert "asynchronous runtime" in text, "keeps the article body"

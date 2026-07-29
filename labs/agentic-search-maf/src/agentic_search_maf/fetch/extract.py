"""HTML → plain text extraction, ported from ``fetch/extract.rs``.

First tries a Readability extraction (via ``readability-lxml``, the same
Firefox Reader View lineage as the Rust ``dom_smoothie`` crate) to drop
navigation/footer/boilerplate, then falls back to a whole-document text walk
so the LLM still gets *something* on search-result pages or JS shells.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

#: Tags whose text content is noise for research purposes.
SKIP_TAGS = ("script", "style", "noscript", "svg", "iframe", "template")

#: Below this many characters, a readability extraction is treated as a miss.
MIN_READABLE_CHARS = 200


def html_to_text(html: str, max_chars: int) -> str:
    """Convert an HTML document into readable plain text, truncated to
    ``max_chars``."""
    text = _readable_text(html)
    if text is None:
        text = _full_document_text(html)
    return _collapse_whitespace(text)[:max_chars]


def _readable_text(html: str) -> str | None:
    """Extract just the main article body via Readability. Returns ``None``
    when no article is found or the result is too short to be real."""
    try:
        from readability import Document

        summary_html = Document(html).summary(html_partial=True)
        text = BeautifulSoup(summary_html, "html.parser").get_text(" ")
    except Exception:
        return None
    if len(text.strip()) < MIN_READABLE_CHARS:
        return None
    return text


def _full_document_text(html: str) -> str:
    """Whole-document visible text, skipping non-content tags. Used as a
    fallback when Readability cannot isolate an article."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(SKIP_TAGS):
        tag.decompose()
    root = soup.body or soup
    return root.get_text(" ")


def _collapse_whitespace(text: str) -> str:
    return " ".join(text.split())

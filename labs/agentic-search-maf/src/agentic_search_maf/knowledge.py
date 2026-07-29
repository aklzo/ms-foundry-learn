"""Accumulated research state, ported from ``agent/knowledge.rs``.

Deduplicated findings plus the URLs and queries already consumed, so the
loop never repeats work. In the MAF workflow the store is shared by the
gatherer / evaluator / reporter executors of a single run (the workflow
factory creates a fresh store per run).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Finding:
    """One verified-as-relevant statement extracted from a source page."""

    statement: str
    source_url: str
    source_title: str
    #: Publication date as stated by the source, if the extractor saw one.
    published_hint: str | None = None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class KnowledgeStore:
    def __init__(self) -> None:
        self._findings: list[Finding] = []
        self._statement_keys: set[str] = set()
        self._visited_urls: set[str] = set()
        self._executed_queries: set[str] = set()

    def add_finding(self, finding: Finding) -> bool:
        """Insert a finding unless an equivalent statement is already stored.
        Returns ``True`` when the finding was new (the novelty signal)."""
        key = _normalize(finding.statement)
        if key in self._statement_keys:
            return False
        self._statement_keys.add(key)
        self._findings.append(finding)
        return True

    @property
    def findings(self) -> list[Finding]:
        return self._findings

    def mark_visited(self, url: str) -> bool:
        if url in self._visited_urls:
            return False
        self._visited_urls.add(url)
        return True

    def is_visited(self, url: str) -> bool:
        return url in self._visited_urls

    def mark_query(self, query: str) -> bool:
        """Record a query as executed. Returns ``False`` if it ran before."""
        key = _normalize(query)
        if key in self._executed_queries:
            return False
        self._executed_queries.add(key)
        return True

    def source_count(self) -> int:
        return len({finding.source_url for finding in self._findings})

    def digest(self, max_chars: int) -> str:
        """Compact numbered digest of all findings for evaluator/reporter
        prompts."""
        out: list[str] = []
        total = 0
        for index, finding in enumerate(self._findings):
            date = finding.published_hint or "date unknown"
            line = f"[{index + 1}] {finding.statement} (source: {finding.source_url} | {date})\n"
            if total + len(line) > max_chars:
                out.append("... (digest truncated)\n")
                break
            out.append(line)
            total += len(line)
        return "".join(out)


def _normalize(text: str) -> str:
    """Case/whitespace-insensitive form used for deduplication."""
    return " ".join(text.split()).lower()

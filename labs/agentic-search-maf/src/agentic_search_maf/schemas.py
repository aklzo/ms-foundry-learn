"""Structured-output schemas for the LLM roles.

In the Rust version these were serde structs deserialized from hand-parsed
JSON. Here they double as MAF ``response_format`` models: providers with
native structured-output support enforce the schema server-side, and the
lenient fallback in :mod:`json_utils` covers providers that do not.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .json_utils import extract_json

SUFFICIENCY_THRESHOLD = 70


class Plan(BaseModel):
    """Initial task decomposition produced by the planner LLM."""

    sub_questions: list[str] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)


class ExtractedFinding(BaseModel):
    statement: str
    published_hint: str | None = None


class Extraction(BaseModel):
    """Extractor output: findings pulled from one fetched page."""

    findings: list[ExtractedFinding] = Field(default_factory=list)


class AspectReview(BaseModel):
    """Review of one quality axis (0-100 plus concrete issues)."""

    score: int = 0
    issues: list[str] = Field(default_factory=list)


class Evaluation(BaseModel):
    """Self-evaluation of the collected knowledge: freshness (is it
    current?), correctness (is it contradiction-free?), coverage (is it
    complete?)."""

    freshness: AspectReview = Field(default_factory=AspectReview)
    correctness: AspectReview = Field(default_factory=AspectReview)
    coverage: AspectReview = Field(default_factory=AspectReview)
    is_sufficient: bool = False
    followup_queries: list[str] = Field(default_factory=list)

    def sufficient(self) -> bool:
        """Guard against an over-optimistic judge: ``is_sufficient`` only
        counts when the per-axis scores back it up."""
        return (
            self.is_sufficient
            and self.freshness.score >= SUFFICIENCY_THRESHOLD
            and self.correctness.score >= SUFFICIENCY_THRESHOLD
            and self.coverage.score >= SUFFICIENCY_THRESHOLD
        )


def parse_structured(response: Any, model: type[BaseModel]) -> BaseModel:
    """Parse a MAF agent response into ``model``.

    Prefers the natively parsed structured output (``response.value``); falls
    back to lenient JSON extraction from the raw text for providers that
    ignore ``response_format`` or models that wrap JSON in prose. The
    ``value`` property raises when the text is not clean JSON, hence the
    broad except.
    """
    try:
        value = getattr(response, "value", None)
    except Exception:
        value = None
    if isinstance(value, model):
        return value
    return model.model_validate(extract_json(response.text))


def parse_extraction(response: Any) -> list[ExtractedFinding]:
    """Lenient parsing of extractor output: small local models occasionally
    emit a bare array or a few malformed entries; salvage every valid finding
    instead of discarding the whole page."""
    try:
        value = getattr(response, "value", None)
    except Exception:
        value = None
    if isinstance(value, Extraction):
        items: list[Any] = [f.model_dump() for f in value.findings]
    else:
        parsed = extract_json(response.text)
        if isinstance(parsed, list):
            items = parsed
        elif isinstance(parsed, dict):
            raw = parsed.get("findings")
            items = raw if isinstance(raw, list) else []
        else:
            return []
    findings: list[ExtractedFinding] = []
    for item in items:
        try:
            finding = ExtractedFinding.model_validate(item)
        except Exception:
            continue
        if finding.statement.strip():
            findings.append(finding)
    return findings

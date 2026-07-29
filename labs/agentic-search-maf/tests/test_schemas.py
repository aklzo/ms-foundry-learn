from dataclasses import dataclass
from typing import Any

from agentic_search_maf.schemas import (
    AspectReview,
    Evaluation,
    parse_extraction,
    parse_structured,
)


@dataclass
class FakeResponse:
    """Stands in for an AgentRunResponse: .value (parsed) and .text (raw)."""

    text: str
    value: Any = None


def review(score: int) -> AspectReview:
    return AspectReview(score=score, issues=[])


def test_sufficiency_requires_flag_and_scores():
    evaluation = Evaluation(
        freshness=review(80),
        correctness=review(90),
        coverage=review(75),
        is_sufficient=True,
    )
    assert evaluation.sufficient()

    evaluation.coverage.score = 50
    assert not evaluation.sufficient(), "low coverage must veto sufficiency"

    evaluation.coverage.score = 75
    evaluation.is_sufficient = False
    assert not evaluation.sufficient(), "judge verdict must be respected"


def test_deserializes_partial_judge_output():
    evaluation = parse_structured(
        FakeResponse(
            text='{"coverage": {"score": 40, "issues": ["missing pricing data"]},'
            ' "followup_queries": ["product pricing 2026"]}'
        ),
        Evaluation,
    )
    assert evaluation.coverage.score == 40
    assert not evaluation.sufficient()
    assert evaluation.followup_queries == ["product pricing 2026"]


def test_parses_wrapped_findings_object():
    findings = parse_extraction(
        FakeResponse(text='{"findings": [{"statement": "Fact", "published_hint": "2026-01-01"}]}')
    )
    assert len(findings) == 1
    assert findings[0].statement == "Fact"


def test_parses_bare_array_output():
    assert len(parse_extraction(FakeResponse(text='[{"statement": "Fact"}]'))) == 1


def test_salvages_valid_entries_among_malformed_ones():
    findings = parse_extraction(
        FakeResponse(
            text='{"findings": ["not an object", {"statement": "Good"}, {"statement": "  "}]}'
        )
    )
    assert len(findings) == 1
    assert findings[0].statement == "Good"


def test_irrelevant_shapes_yield_no_findings():
    assert parse_extraction(FakeResponse(text='{"other": 1}')) == []

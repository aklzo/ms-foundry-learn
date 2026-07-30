"""構造化出力スキーマと lenient パーサのオフラインテスト(ネットワーク不要)。"""

import json
from dataclasses import dataclass
from typing import Any

import pytest
from pydantic import ValidationError

from research_handoff_maf.schemas import (
    ResearchPlan,
    ResearchReport,
    SchemaError,
    TriageDecision,
    extract_json,
    parse_structured,
)


@dataclass
class FakeResponse:
    text: str
    value: Any = None


DECISION_DICT = {
    "plan": {"topic": "t", "search_queries": ["q"], "focus_areas": ["f"]},
    "handoff_to": "research",
    "reason": "r",
}


def test_parse_structured_prefers_native_value() -> None:
    decision = TriageDecision(
        plan=ResearchPlan(topic="t"), handoff_to="editor", reason="native"
    )
    parsed = parse_structured(FakeResponse(text="garbage", value=decision), TriageDecision)
    assert parsed is decision


def test_parse_structured_falls_back_to_json_text() -> None:
    parsed = parse_structured(
        FakeResponse(text=json.dumps(DECISION_DICT)), TriageDecision
    )
    assert parsed.handoff_to == "research"
    assert parsed.plan.search_queries == ["q"]


def test_parse_structured_extracts_json_from_prose() -> None:
    text = f"Sure! Here you go:\n```json\n{json.dumps(DECISION_DICT)}\n```"
    parsed = parse_structured(FakeResponse(text=text), TriageDecision)
    assert parsed.handoff_to == "research"


def test_parse_structured_raises_on_no_json() -> None:
    with pytest.raises(SchemaError):
        parse_structured(FakeResponse(text="no json here"), TriageDecision)


def test_parse_structured_raises_on_schema_mismatch() -> None:
    bad = dict(DECISION_DICT, handoff_to="phone_a_friend")
    with pytest.raises(SchemaError):
        parse_structured(FakeResponse(text=json.dumps(bad)), TriageDecision)


def test_triage_decision_rejects_unknown_route() -> None:
    with pytest.raises(ValidationError):
        TriageDecision(plan=ResearchPlan(topic="t"), handoff_to="nowhere")


def test_research_report_defaults_are_lenient() -> None:
    """モデルが outline/sources/word_count を落としても本文があれば成立する。"""
    report = ResearchReport.model_validate({"title": "T", "report": "body"})
    assert report.outline == [] and report.sources == [] and report.word_count == 0


def test_extract_json_balanced_slice_with_nested_braces() -> None:
    text = 'prefix {"a": {"b": "with } inside string"}, "c": [1, 2]} suffix'
    assert extract_json(text) == {"a": {"b": "with } inside string"}, "c": [1, 2]}

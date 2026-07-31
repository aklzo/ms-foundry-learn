"""構造化出力スキーマと lenient パーサのオフラインテスト。"""

from dataclasses import dataclass
from typing import Any

import pytest

from critique_loop_maf.schemas import (
    CritiqueVerdict,
    SchemaError,
    extract_json,
    parse_structured,
)


@dataclass
class FakeResponse:
    text: str
    value: Any = None


def test_extract_json_plain() -> None:
    assert extract_json('{"verdict": "accept", "critiques": []}') == {
        "verdict": "accept",
        "critiques": [],
    }


def test_extract_json_wrapped_in_prose() -> None:
    text = 'Here is my review:\n{"verdict": "revise", "critiques": ["a", "b"]}\nThanks!'
    assert extract_json(text)["critiques"] == ["a", "b"]


def test_extract_json_missing_raises() -> None:
    with pytest.raises(SchemaError):
        extract_json("no json here")


def test_parse_structured_prefers_native_value() -> None:
    verdict = CritiqueVerdict(verdict="accept")
    parsed = parse_structured(FakeResponse(text="garbage", value=verdict), CritiqueVerdict)
    assert parsed is verdict


def test_parse_structured_falls_back_to_text() -> None:
    parsed = parse_structured(
        FakeResponse(text='{"verdict": "revise", "critiques": ["x"]}'), CritiqueVerdict
    )
    assert parsed.verdict == "revise"
    assert parsed.critiques == ["x"]


def test_parse_structured_rejects_invalid_verdict() -> None:
    with pytest.raises(SchemaError):
        parse_structured(
            FakeResponse(text='{"verdict": "maybe", "critiques": []}'), CritiqueVerdict
        )


def test_critiques_default_to_empty() -> None:
    parsed = parse_structured(FakeResponse(text='{"verdict": "accept"}'), CritiqueVerdict)
    assert parsed.critiques == []

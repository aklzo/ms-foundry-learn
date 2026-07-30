"""構造化出力スキーマと lenient パーサのオフラインテスト(ネットワーク不要)。

元アプリの grade_documents は ``re.search(r'\\{.*\\}', response)`` +
``json.loads`` で JSON を緩く拾っていた。本移植の extract_json(balanced
slice)が同等以上に寛容であることをここで固定する。
"""

import json
from dataclasses import dataclass
from typing import Any

import pytest
from pydantic import ValidationError

from corrective_rag_maf.schemas import (
    GradeScore,
    SchemaError,
    extract_json,
    parse_structured,
)


@dataclass
class FakeResponse:
    text: str
    value: Any = None


def test_parse_structured_prefers_native_value() -> None:
    score = GradeScore(score="no")
    parsed = parse_structured(FakeResponse(text="garbage", value=score), GradeScore)
    assert parsed is score


def test_parse_structured_falls_back_to_json_text() -> None:
    parsed = parse_structured(FakeResponse(text='{"score": "yes"}'), GradeScore)
    assert parsed.score == "yes"


def test_parse_structured_extracts_json_from_prose() -> None:
    """元実装の regex 抽出パス(散文で包まれた JSON)に対応。"""
    text = 'The document is relevant to the question. {"score": "yes"} Hope this helps.'
    parsed = parse_structured(FakeResponse(text=text), GradeScore)
    assert parsed.score == "yes"


def test_parse_structured_extracts_json_from_code_fence() -> None:
    text = 'Here is my grade:\n```json\n{"score": "no"}\n```'
    parsed = parse_structured(FakeResponse(text=text), GradeScore)
    assert parsed.score == "no"


def test_parse_structured_raises_on_no_json() -> None:
    with pytest.raises(SchemaError):
        parse_structured(FakeResponse(text="the document looks fine to me"), GradeScore)


def test_parse_structured_raises_on_schema_mismatch() -> None:
    """score が yes/no 以外なら Literal 検証で弾く(元実装は score.get() の
    緩い比較で "maybe" を no 扱いにしていた — 移植では明示的にエラー →
    採点側で「安全側に残す」処理に落ちる)。"""
    with pytest.raises(SchemaError):
        parse_structured(FakeResponse(text='{"score": "maybe"}'), GradeScore)


def test_grade_score_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError):
        GradeScore(score="maybe")


def test_extract_json_balanced_slice_with_nested_braces() -> None:
    text = 'prefix {"a": {"b": "with } inside string"}, "c": [1, 2]} suffix'
    assert extract_json(text) == {"a": {"b": "with } inside string"}, "c": [1, 2]}


def test_extract_json_plain_object() -> None:
    assert json.dumps(extract_json('  {"score": "yes"}  ')) == '{"score": "yes"}'

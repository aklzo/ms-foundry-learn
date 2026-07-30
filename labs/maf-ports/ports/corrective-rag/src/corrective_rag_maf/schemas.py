"""構造化出力スキーマ + lenient パーサ。

元アプリの対応:
- ``GradeScore``: grade_documents ノードが LLM に要求していた
  ``{"score": "yes"}`` / ``{"score": "no"}`` の JSON。元実装は
  ``re.search(r'\\{.*\\}', response)`` + ``json.loads`` で緩く抽出していた —
  本移植の ``extract_json``(balanced slice)はその上位互換で、さらに MAF の
  ネイティブ構造化出力(``ChatOptions(response_format=...)`` → ``.value``)を
  優先して使う。

``extract_json`` / ``parse_structured`` は ports/research-handoff の
schemas.py から移植(元は labs/agentic-search-maf。相対 import できないため
コピー)。
"""

from __future__ import annotations

import contextlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ValidationError


class SchemaError(RuntimeError):
    """構造化出力が期待スキーマとして解釈できない。"""


class GradeScore(BaseModel):
    """文書採点の構造化出力(元アプリの {"score": "yes"/"no"} と同一形)。

    元実装ではこの判定が ``run_web_search`` フラグ("Yes"/"No" の文字列)に
    集約され、conditional edge の分岐条件になっていた。移植では bool
    (GradeOutcome.needs_web_search)に落とし、switch-case エッジで分岐する。
    """

    score: Literal["yes", "no"]


def parse_structured(response: Any, model: type[BaseModel]) -> Any:
    """MAF エージェント応答を ``model`` として解釈する。

    ネイティブ構造化出力(``response.value``)を優先し、response_format を
    無視するプロバイダや JSON を散文で包むモデルには生テキストからの lenient
    抽出でフォールバックする。``value`` プロパティはテキストが素の JSON で
    ないと例外を投げ得るため broad except。
    """
    value = None
    with contextlib.suppress(Exception):
        value = getattr(response, "value", None)
    if isinstance(value, model):
        return value
    try:
        return model.model_validate(extract_json(response.text))
    except ValidationError as exc:
        raise SchemaError(f"response does not match {model.__name__}: {exc}") from exc


def extract_json(text: str) -> Any:
    """LLM 出力から最初の JSON オブジェクト/配列を取り出す。"""
    try:
        return json.loads(text.strip())
    except (json.JSONDecodeError, ValueError):
        pass
    candidate = _balanced_json_slice(text)
    if candidate is None:
        raise SchemaError(f"no JSON found in: {_preview(text)}")
    try:
        return json.loads(candidate)
    except (json.JSONDecodeError, ValueError) as exc:
        raise SchemaError(f"invalid JSON ({exc}): {_preview(candidate)}") from exc


def _balanced_json_slice(text: str) -> str | None:
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        return None
    start = min(starts)
    open_char = text[start]
    close_char = "}" if open_char == "{" else "]"

    depth = 0
    in_string = False
    escaped = False
    for offset, char in enumerate(text[start:]):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return text[start : start + offset + 1]
    return None


def _preview(text: str) -> str:
    return text.strip()[:200]

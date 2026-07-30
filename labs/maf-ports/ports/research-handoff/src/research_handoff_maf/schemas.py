"""構造化出力スキーマ + lenient パーサ。

元アプリのツール対応:
- ``ResearchPlan`` / ``ResearchReport``: 元 research_agent.py の Pydantic
  モデル(``output_type=``)をそのまま移植。MAF では ``ChatOptions(
  response_format=...)`` に渡してネイティブ構造化出力にする。
- ``TriageDecision``: 追加モデル。元の handoff(SDK が内部生成するツール
  呼び出しで LLM が委譲先を選ぶ)を「構造化出力によるルーティング判断+
  switch-case エッジ」に置き換えるため、委譲先(``handoff_to``)を
  データとして返させる。

``extract_json`` / ``parse_structured`` は labs/agentic-search-maf の
json_utils.py / schemas.py から移植(相対 import できないためコピー)。
"""

from __future__ import annotations

import contextlib
import json
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError


class SchemaError(RuntimeError):
    """構造化出力が期待スキーマとして解釈できない。"""


class ResearchPlan(BaseModel):
    """トリアージが立てるリサーチ計画(元アプリの ResearchPlan と同一形)。"""

    topic: str
    search_queries: list[str] = Field(default_factory=list)
    focus_areas: list[str] = Field(default_factory=list)


class TriageDecision(BaseModel):
    """トリアージの構造化出力: 計画+委譲先。

    元アプリではこの「委譲先の選択」は handoff ツール呼び出しとして LLM の
    自由裁量だった(かつ ``output_type=ResearchPlan`` と競合し、handoff が
    発火すると final_output が ResearchPlan でなくなる)。移植では判断を
    データに落とし、グラフのエッジ条件で分岐させる。
    """

    plan: ResearchPlan
    handoff_to: Literal["research", "editor"]
    reason: str = ""


class ResearchReport(BaseModel):
    """最終レポート(元アプリの ResearchReport と同一形)。"""

    title: str
    outline: list[str] = Field(default_factory=list)
    report: str
    sources: list[str] = Field(default_factory=list)
    word_count: int = 0


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

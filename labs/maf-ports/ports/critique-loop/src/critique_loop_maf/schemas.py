"""構造化出力スキーマ + lenient パーサ。

元アプリの対応:
- ``CritiqueVerdict``: 元の critique_answer は「'•' 始まりの箇条書き」という
  自由テキストを返させ、**改訂するかどうかの判断は存在しなかった**
  (max_iterations 回、無条件に批評→改訂を回す)。移植では批評を構造化出力
  (継続/終了判断 ``verdict`` + 改善指示 ``critiques``)に落とし、
  switch-case エッジの分岐条件にする(= 「合格なら早期終了」を追加。
  上限回数は元実装と同じ)。

``extract_json`` / ``parse_structured`` は ports/corrective-rag の schemas.py
から移植(元は labs/agentic-search-maf。相対 import できないためコピー)。
"""

from __future__ import annotations

import contextlib
import json
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError


class SchemaError(RuntimeError):
    """構造化出力が期待スキーマとして解釈できない。"""


class CritiqueVerdict(BaseModel):
    """批評の構造化出力: 継続/終了判断+改善指示。

    - ``verdict="accept"``: 現ドラフトは十分な品質 → ループを終了(早期終了)
    - ``verdict="revise"``: ``critiques`` を改訂プロンプトに載せて改訂へ

    元アプリの「'•' 箇条書きの批評テキスト」が ``critiques``(1 要素 =
    1 批評点)に対応する。``revise`` なのに批評が空のときは改訂プロンプトに
    載せるものがないため、workflow 側で accept に正規化する。
    """

    verdict: Literal["accept", "revise"]
    critiques: list[str] = Field(default_factory=list)


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

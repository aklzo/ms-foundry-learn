"""Lenient JSON extraction from LLM output, ported from ``llm/json.rs``.

Models often wrap JSON in code fences or prose; this finds the first
balanced ``{...}`` / ``[...]`` region (string-aware) and parses it.
"""

from __future__ import annotations

import json
from typing import Any

from .errors import LlmResponseError


def extract_json(text: str) -> Any:
    """Extract the first JSON object or array from LLM output."""
    try:
        return json.loads(text.strip())
    except (json.JSONDecodeError, ValueError):
        pass
    candidate = _balanced_json_slice(text)
    if candidate is None:
        raise LlmResponseError(f"no JSON found in: {_preview(text)}")
    try:
        return json.loads(candidate)
    except (json.JSONDecodeError, ValueError) as exc:
        raise LlmResponseError(f"invalid JSON ({exc}): {_preview(candidate)}") from exc


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

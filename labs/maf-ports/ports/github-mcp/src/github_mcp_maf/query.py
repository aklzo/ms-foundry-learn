"""1 クエリの実行ロジック — 元アプリの run_github_agent + クエリ組み立ての移植。

元アプリの挙動(github_agent.py 103 / 119-123 行)を忠実に踏襲する:

- リポジトリ指定がクエリ本文に含まれていなければ ``"{query} in {repo}"`` を
  連結する(``--repo`` は Streamlit の Repository 入力欄に対応)
- 実行は ``asyncio.wait_for(..., timeout=120.0)`` — 120 秒でタイムアウト
- 空応答は例外にしない(元アプリは response.content をそのまま表示する)
"""

from __future__ import annotations

import asyncio

from .agents import SupportsRun

#: 元アプリの asyncio.wait_for(..., timeout=120.0) と同値
DEFAULT_TIMEOUT_SECONDS = 120.0


def build_full_query(question: str, repo: str | None = None) -> str:
    """元アプリ 119-123 行のクエリ連結を原文どおり再現する。"""
    if repo and repo not in question:
        return f"{question} in {repo}"
    return question


async def run_query(
    agent: SupportsRun,
    question: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """エージェントを 1 回実行して応答テキストを返す(タイムアウト付き)。

    タイムアウト時は TimeoutError が送出される(CLI が元アプリと同旨の
    エラーメッセージに変換する)。
    """
    response = await asyncio.wait_for(agent.run(question), timeout)
    return getattr(response, "text", "") or ""

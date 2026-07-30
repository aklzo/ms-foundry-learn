"""クエリ組み立てと応答パスのオフラインテスト(ScriptedAgent)。
パターンは ports/travel-memory/tests/test_chat_turn.py の ScriptedAgent を踏襲。

検証項目(元アプリ github_agent.py の挙動の固定):
- 119-123 行: --repo がクエリ本文に無いときだけ "in <repo>" を連結
- 103 行: asyncio.wait_for によるタイムアウト
- 空応答は例外にしない(元アプリは content をそのまま表示)
"""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

import pytest

from github_mcp_maf.query import DEFAULT_TIMEOUT_SECONDS, build_full_query, run_query

REPO = "microsoft/agent-framework"


@dataclass
class FakeResponse:
    text: str


class ScriptedAgent:
    """受け取ったメッセージを記録し、決められた応答を順に返す
    (応答リストが尽きたら最後のものを繰り返す)。"""

    def __init__(self, replies: Sequence[str] = ("ok",)) -> None:
        self.replies = list(replies)
        self.received: list[str] = []

    async def run(self, message: str) -> FakeResponse:
        index = min(len(self.received), len(self.replies) - 1)
        self.received.append(message)
        return FakeResponse(text=self.replies[index])


class SlowAgent:
    async def run(self, message: str) -> FakeResponse:
        await asyncio.sleep(0.5)
        return FakeResponse(text="too late")


# --- build_full_query(元アプリ 119-123 行)---


def test_repo_is_appended_when_absent_from_query() -> None:
    assert build_full_query("Show me recent merged PRs", REPO) == (
        f"Show me recent merged PRs in {REPO}"
    )


def test_repo_is_not_duplicated_when_already_in_query() -> None:
    question = f"What PRs need review in {REPO}?"
    assert build_full_query(question, REPO) == question


def test_no_repo_leaves_query_unchanged() -> None:
    assert build_full_query("Show repository health metrics") == "Show repository health metrics"
    assert build_full_query("Show repository health metrics", None) == (
        "Show repository health metrics"
    )


# --- run_query(元アプリ run_github_agent 相当)---


async def test_run_query_passes_question_and_returns_text() -> None:
    agent = ScriptedAgent(replies=("There are 3 open PRs.",))

    answer = await run_query(agent, f"What PRs need review? in {REPO}")

    assert answer == "There are 3 open PRs."
    assert agent.received == [f"What PRs need review? in {REPO}"]


async def test_run_query_empty_reply_returns_empty_string() -> None:
    """元アプリは空応答を例外にしない(travel-memory の元アプリとは異なる)。"""
    agent = ScriptedAgent(replies=("",))

    assert await run_query(agent, "anything") == ""


async def test_run_query_times_out() -> None:
    with pytest.raises(TimeoutError):
        await run_query(SlowAgent(), "slow question", timeout=0.01)


def test_default_timeout_matches_original_app() -> None:
    assert DEFAULT_TIMEOUT_SECONDS == 120.0

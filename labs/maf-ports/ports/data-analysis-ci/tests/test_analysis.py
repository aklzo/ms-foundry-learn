"""会話フローと応答抽出のオフラインテスト(ScriptedAgent)。
パターンは ports/github-mcp/tests/test_query.py の ScriptedAgent を踏襲。

検証項目:
- build_analysis_prompt: ファイル名と質問がプロンプトに載る(元アプリの
  「'uploaded_data' テーブル」指定の per-run 版)
- run_analysis: タイムアウト・空応答(例外にしない)
- extract_analysis: 実 ``Message`` / ``Content``(code_interpreter_tool_call /
  code_interpreter_tool_result)からコード・ログ・画像を取り出す
"""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest

from data_analysis_ci_maf.analysis import (
    DEFAULT_TIMEOUT_SECONDS,
    build_analysis_prompt,
    extract_analysis,
    run_analysis,
)


@dataclass
class FakeResponse:
    text: str
    messages: list[Any] = field(default_factory=list)


class ScriptedAgent:
    """受け取ったメッセージを記録し、決められた応答を順に返す
    (応答リストが尽きたら最後のものを繰り返す)。"""

    def __init__(self, replies: Sequence[FakeResponse] = (FakeResponse(text="ok"),)) -> None:
        self.replies = list(replies)
        self.received: list[str] = []

    async def run(self, message: str) -> FakeResponse:
        index = min(len(self.received), len(self.replies) - 1)
        self.received.append(message)
        return self.replies[index]


class SlowAgent:
    async def run(self, message: str) -> FakeResponse:
        await asyncio.sleep(0.5)
        return FakeResponse(text="too late")


# --- build_analysis_prompt ---


def test_prompt_contains_filename_and_question() -> None:
    prompt = build_analysis_prompt("月別売上の傾向は?", "sample_sales.csv")

    assert "sample_sales.csv" in prompt
    assert "月別売上の傾向は?" in prompt
    assert "/mnt/data" in prompt  # コンテナ内のファイル所在の案内


# --- run_analysis(会話フロー)---


async def test_run_analysis_passes_prompt_and_returns_text() -> None:
    agent = ScriptedAgent(replies=(FakeResponse(text="Total revenue is 3,225,050."),))
    prompt = build_analysis_prompt("合計売上は?", "sample_sales.csv")

    result = await run_analysis(agent, prompt)

    assert result.text == "Total revenue is 3,225,050."
    assert agent.received == [prompt]
    assert result.code_blocks == []


async def test_run_analysis_empty_reply_returns_empty_result() -> None:
    """元アプリは response.content をそのまま表示(空でも例外にしない)。"""
    agent = ScriptedAgent(replies=(FakeResponse(text=""),))

    result = await run_analysis(agent, "anything")

    assert result.text == ""


async def test_run_analysis_times_out() -> None:
    with pytest.raises(TimeoutError):
        await run_analysis(SlowAgent(), "slow question", timeout=0.01)


def test_default_timeout_bounds_container_startup() -> None:
    assert DEFAULT_TIMEOUT_SECONDS == 300.0


# --- extract_analysis(実 Content での抽出)---


def make_real_response() -> Any:
    """実 MAF 型で code_interpreter の call / result を含む応答を組む。"""
    pytest.importorskip("agent_framework")
    from agent_framework import Content, Message

    code = "import pandas as pd\ndf = pd.read_csv('/mnt/data/sample_sales.csv')\ndf.sum()"
    contents = [
        Content.from_code_interpreter_tool_call(
            call_id="ci_1",
            inputs=[Content.from_text(text=code)],
        ),
        Content.from_code_interpreter_tool_result(
            call_id="ci_1",
            outputs=[
                Content.from_text(text="revenue    3225050"),
                Content.from_uri(uri="https://files.example/chart.png", media_type="image"),
            ],
        ),
        Content.from_text(text="Total revenue is 3,225,050."),
    ]
    return FakeResponse(
        text="Total revenue is 3,225,050.",
        messages=[Message("assistant", contents=contents)],
    )


def test_extract_analysis_pulls_code_logs_and_images() -> None:
    result = extract_analysis(make_real_response())

    assert result.text == "Total revenue is 3,225,050."
    assert len(result.code_blocks) == 1
    assert "pd.read_csv('/mnt/data/sample_sales.csv')" in result.code_blocks[0]
    assert result.logs == ["revenue    3225050"]
    assert result.image_uris == ["https://files.example/chart.png"]


def test_extract_analysis_tolerates_plain_text_response() -> None:
    """code_interpreter を使わず即答したケース(ツール強制はしていない)。"""
    result = extract_analysis(FakeResponse(text="It has 30 rows."))

    assert result.text == "It has 30 rows."
    assert result.code_blocks == []
    assert result.logs == []
    assert result.image_uris == []


async def test_run_analysis_extracts_from_scripted_flow() -> None:
    """ScriptedAgent での一気通貫: プロンプト → 応答 → 抽出。"""
    agent = ScriptedAgent(replies=(make_real_response(),))
    prompt = build_analysis_prompt("合計と上位カテゴリは?", "sample_sales.csv")

    result = await run_analysis(agent, prompt)

    assert agent.received == [prompt]
    assert "3225050" in result.logs[0].replace(",", "")
    assert result.code_blocks and "pandas" in result.code_blocks[0]

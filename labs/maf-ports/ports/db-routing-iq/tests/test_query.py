"""クエリ実行・ツール呼び出し抽出・ルーティング期待のオフラインテスト。

- run_query / response_text: ScriptedAgent での応答パス(github-mcp の方針)
- summarize_tool_calls: 応答メッセージからのルーティング観測の抽出
- ルーティング期待(データ駆動): eval_dataset.jsonl の各ケースについて
  「期待ソースのコーパスに期待ファクトが実在し、かつ他ドメインには無い」
  ことを固定する。これが崩れると、ライブスモークの「正しいソース由来か」の
  検証が無意味になる(実検索はライブのみ — PORTING.md §4)。
"""

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from db_routing_iq_maf.query import (
    DEFAULT_TIMEOUT_SECONDS,
    response_text,
    run_query,
    summarize_tool_calls,
)

PORT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PORT_ROOT / "data"
DATASET_PATH = Path(__file__).parent / "eval_dataset.jsonl"

DOMAIN_DIRS = ("products", "support", "finance")


def load_dataset() -> list[dict]:
    return [
        json.loads(line)
        for line in DATASET_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def domain_corpus(domain: str) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted((DATA_DIR / domain).glob("*.md"))
    )


# --- run_query / response_text(ScriptedAgent)---


@dataclass
class FakeResponse:
    text: str
    messages: list = field(default_factory=list)


class ScriptedAgent:
    def __init__(self, reply: str = "ok") -> None:
        self.reply = reply
        self.received: list[str] = []

    async def run(self, message: str) -> FakeResponse:
        self.received.append(message)
        return FakeResponse(text=self.reply)


class SlowAgent:
    async def run(self, message: str) -> FakeResponse:
        await asyncio.sleep(0.5)
        return FakeResponse(text="too late")


async def test_run_query_passes_question_and_returns_response() -> None:
    agent = ScriptedAgent(reply="重量は 1.2kg です。")

    response = await run_query(agent, "Aurora X10 の重さは?")

    assert agent.received == ["Aurora X10 の重さは?"]
    assert response_text(response) == "重量は 1.2kg です。"


async def test_run_query_times_out() -> None:
    with pytest.raises(TimeoutError):
        await run_query(SlowAgent(), "slow", timeout=0.01)


def test_response_text_tolerates_empty_and_missing() -> None:
    """空応答は例外にしない(元アプリはそのまま表示する)。"""
    assert response_text(FakeResponse(text="")) == ""
    assert response_text(object()) == ""


def test_default_timeout_is_operational_addition() -> None:
    """元アプリに全体タイムアウトは無い — CLI 安全弁としての追加差分(README)。"""
    assert DEFAULT_TIMEOUT_SECONDS == 180.0


# --- summarize_tool_calls(ルーティング観測)---


@dataclass
class FakeCall:
    name: str
    call_id: str


@dataclass
class FakeText:
    text: str


@dataclass
class FakeMessage:
    contents: list


def test_summarize_tool_calls_extracts_names_in_order_without_duplicates() -> None:
    response = FakeResponse(
        text="answer",
        messages=[
            FakeMessage(contents=[FakeCall("knowledge_base_retrieve", "c1")]),
            FakeMessage(contents=[FakeText("intermediate")]),
            FakeMessage(
                contents=[
                    FakeCall("knowledge_base_retrieve", "c2"),
                    FakeCall("web_search", "c3"),
                ]
            ),
        ],
    )

    assert summarize_tool_calls(response) == ["knowledge_base_retrieve", "web_search"]


def test_summarize_tool_calls_handles_responses_without_messages() -> None:
    assert summarize_tool_calls(object()) == []
    assert summarize_tool_calls(FakeResponse(text="x")) == []


# --- ルーティング期待(データ駆動: eval_dataset ↔ data/ の整合)---


def test_dataset_covers_all_domains_and_web_fallback() -> None:
    sources = [case["expected_source"] for case in load_dataset()]

    assert set(sources) == {"products", "support", "finance", "web"}
    # ライブスモークの最小要件: 3 ドメイン各 1 問+ドメイン外 1 問
    assert all(sources.count(domain) >= 1 for domain in DOMAIN_DIRS)


@pytest.mark.parametrize(
    "case",
    [case for case in load_dataset() if case["expected_source"] != "web"],
    ids=lambda case: case["expected_fact"],
)
def test_expected_fact_exists_only_in_expected_domain(case: dict) -> None:
    """期待ファクトが期待ドメインのコーパスに実在し、他ドメインには無いこと。
    (= 正答が返れば正しいソースから引いた、と推論できる根拠)"""
    expected_domain = case["expected_source"]
    fact = case["expected_fact"]

    assert fact in domain_corpus(expected_domain), (
        f"{fact!r} が data/{expected_domain}/ に見つからない — データセットとコーパスの不整合"
    )
    for other in DOMAIN_DIRS:
        if other != expected_domain:
            assert fact not in domain_corpus(other), (
                f"{fact!r} が data/{other}/ にもある — ソース検証が曖昧になる"
            )


def test_web_case_has_no_corpus_fact() -> None:
    web_cases = [case for case in load_dataset() if case["expected_source"] == "web"]

    assert len(web_cases) == 1
    assert "expected_fact" not in web_cases[0]


def test_each_domain_has_three_or_more_documents() -> None:
    """タスク要件: ラボ用文書を各ドメイン 3〜4 篇同梱する。"""
    for domain in DOMAIN_DIRS:
        files = list((DATA_DIR / domain).glob("*.md"))
        assert len(files) >= 3, f"data/{domain}/ の文書が {len(files)} 篇しかない"

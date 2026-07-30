"""ワークフローのオフラインテスト。LLM は scripted fake(ネットワーク不要)。
パターンは ports/trend-analysis/tests/test_workflow.py の ScriptedAgent を踏襲。

検証項目(Port 3 の要点):
- トリアージの分岐: handoff_to == "research" で research 経由、"editor" で直行
- handoff 先が受け取るコンテキスト: research は計画(クエリ・focus areas)、
  editor は元クエリ+research 要約+保存ファクト
- 構造化出力のパース: ネイティブ(.value)/ 散文包み JSON / パース失敗時の
  fallback(元アプリの既定計画フォールバックの踏襲)
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pytest

pytest.importorskip("agent_framework")

from research_handoff_maf.agents import ResearchHandoffAgents
from research_handoff_maf.schemas import ResearchPlan, TriageDecision
from research_handoff_maf.tools import FactStore
from research_handoff_maf.workflow import (
    HandoffDecided,
    ResearchHandoffResult,
    StageDone,
    build_research_workflow,
)

TOPIC = "best affordable espresso machines for a French press upgrader"

TRIAGE_RESEARCH_JSON = json.dumps(
    {
        "plan": {
            "topic": "Affordable espresso machines",
            "search_queries": ["espresso machine under 500 review", "best entry espresso 2026"],
            "focus_areas": ["price/quality balance", "ease of maintenance"],
        },
        "handoff_to": "research",
        "reason": "product landscape changes quickly",
    }
)

TRIAGE_EDITOR_JSON = json.dumps(
    {
        "plan": {
            "topic": "TCP vs UDP",
            "search_queries": [],
            "focus_areas": ["reliability", "latency"],
        },
        "handoff_to": "editor",
        "reason": "stable textbook knowledge",
    }
)

REPORT_JSON = json.dumps(
    {
        "title": "Espresso Machines on a Budget",
        "outline": ["Intro", "Top picks", "Verdict"],
        "report": "# Espresso Machines on a Budget\n\nLong report body...",
        "sources": ["https://example.com/review"],
        "word_count": 1200,
    }
)


@dataclass
class FakeResponse:
    text: str
    value: Any = None


class ScriptedAgent:
    """受け取ったメッセージを記録し、決められた応答を返す。
    ``on_run`` で実行中の副作用(ツール呼び出し相当)を模倣できる。"""

    def __init__(
        self,
        reply: str,
        value: Any = None,
        on_run: Callable[[], None] | None = None,
    ) -> None:
        self.reply = reply
        self.value = value
        self.on_run = on_run
        self.received: list[str] = []

    async def run(self, message: str) -> FakeResponse:
        self.received.append(message)
        if self.on_run is not None:
            self.on_run()
        return FakeResponse(text=self.reply, value=self.value)


@dataclass
class Harness:
    agents: ResearchHandoffAgents
    triage: ScriptedAgent
    research: ScriptedAgent
    editor: ScriptedAgent
    fact_store: FactStore
    results: list[ResearchHandoffResult] = field(default_factory=list)
    decisions: list[HandoffDecided] = field(default_factory=list)
    stages: list[StageDone] = field(default_factory=list)

    async def run(self, topic: str = TOPIC) -> ResearchHandoffResult:
        workflow = build_research_workflow(self.agents, self.fact_store)
        async for event in workflow.run(topic, stream=True):
            if event.type == "intermediate" and isinstance(event.data, HandoffDecided):
                self.decisions.append(event.data)
            elif event.type == "intermediate" and isinstance(event.data, StageDone):
                self.stages.append(event.data)
            elif event.type == "output":
                self.results.append(event.data)
        assert len(self.results) == 1, "最終出力はちょうど 1 回であるべき"
        return self.results[0]


def make_harness(
    triage_reply: str = TRIAGE_RESEARCH_JSON,
    triage_value: Any = None,
    research_reply: str = "Concise research summary. Machine X praised for value.",
    editor_reply: str = REPORT_JSON,
    save_facts: bool = True,
) -> Harness:
    fact_store = FactStore()

    def on_research_run() -> None:
        if save_facts:
            fact_store.add("Machine X costs $450", "https://example.com/review")

    triage = ScriptedAgent(triage_reply, value=triage_value)
    research = ScriptedAgent(research_reply, on_run=on_research_run)
    editor = ScriptedAgent(editor_reply)
    return Harness(
        agents=ResearchHandoffAgents(triage=triage, research=research, editor=editor),
        triage=triage,
        research=research,
        editor=editor,
        fact_store=fact_store,
    )


# --- トリアージ分岐 ---------------------------------------------------------


async def test_research_route_runs_research_then_editor() -> None:
    h = make_harness()
    result = await h.run()

    assert len(h.triage.received) == 1
    assert len(h.research.received) == 1
    assert len(h.editor.received) == 1
    assert result.handoff_to == "research"
    assert result.research_md is not None

    # トリアージには元アプリの実行プロンプト(原文)が渡る
    assert f"Research this topic thoroughly: {TOPIC}" in h.triage.received[0]


async def test_editor_route_skips_research() -> None:
    h = make_harness(triage_reply=TRIAGE_EDITOR_JSON)
    result = await h.run("difference between TCP and UDP")

    assert len(h.research.received) == 0, "editor 直行では research を呼ばない"
    assert len(h.editor.received) == 1
    assert result.handoff_to == "editor"
    assert result.research_md is None
    assert result.facts == []
    # 直行プロンプトには「Web リサーチをしていない」ことが明示される
    assert "No web research was performed" in h.editor.received[0]
    assert "difference between TCP and UDP" in h.editor.received[0]


# --- handoff 先が受け取るコンテキスト --------------------------------------


async def test_research_prompt_carries_plan_context() -> None:
    h = make_harness()
    await h.run()

    prompt = h.research.received[0]
    # 計画のクエリと focus areas が handoff 先に渡る
    assert "espresso machine under 500 review" in prompt
    assert "best entry espresso 2026" in prompt
    assert "price/quality balance" in prompt
    assert "Affordable espresso machines" in prompt


async def test_editor_prompt_carries_query_summary_and_facts() -> None:
    h = make_harness()
    result = await h.run()

    prompt = h.editor.received[0]
    assert TOPIC in prompt  # 元クエリ
    assert "Machine X praised for value" in prompt  # research 要約
    assert "Machine X costs $450" in prompt  # 保存ファクト
    assert "https://example.com/review" in prompt  # ファクトの出典

    # ファクトは最終成果物にも残る(元アプリの Collected Facts 相当)
    assert [f.fact for f in result.facts] == ["Machine X costs $450"]


# --- 構造化出力のパース -----------------------------------------------------


async def test_triage_native_value_path() -> None:
    """ネイティブ構造化出力(.value が model インスタンス)を優先して使う。"""
    decision = TriageDecision(
        plan=ResearchPlan(topic="t", search_queries=["q1"], focus_areas=["f1"]),
        handoff_to="editor",
        reason="native value",
    )
    h = make_harness(triage_reply="(not json)", triage_value=decision)
    result = await h.run()

    assert result.handoff_to == "editor"
    assert result.reason == "native value"


async def test_triage_json_wrapped_in_prose() -> None:
    wrapped = f"Here is my decision:\n```json\n{TRIAGE_RESEARCH_JSON}\n```\nDone."
    h = make_harness(triage_reply=wrapped)
    result = await h.run()

    assert result.handoff_to == "research"
    assert result.plan.search_queries == [
        "espresso machine under 500 review",
        "best entry espresso 2026",
    ]


async def test_triage_parse_failure_falls_back_to_research() -> None:
    """元アプリの fallback(ResearchPlan が取れなければ既定計画で続行)を踏襲。"""
    h = make_harness(triage_reply="I think we should look into this topic.")
    result = await h.run()

    assert result.handoff_to == "research"
    assert result.plan.search_queries == [f"Researching {TOPIC}"]
    assert result.plan.focus_areas == [f"General information about {TOPIC}"]
    assert "fallback" in result.reason
    assert len(h.research.received) == 1  # 既定計画で research が実行される


async def test_triage_unknown_route_falls_back() -> None:
    """handoff_to が未知の値なら Literal 検証で弾かれ fallback になる。"""
    bad = json.dumps(
        {
            "plan": {"topic": "t", "search_queries": [], "focus_areas": []},
            "handoff_to": "phone_a_friend",
            "reason": "?",
        }
    )
    h = make_harness(triage_reply=bad)
    result = await h.run()

    assert result.handoff_to == "research"
    assert "fallback" in result.reason


async def test_editor_report_parsed_from_structured_output() -> None:
    h = make_harness()
    result = await h.run()

    assert result.report.title == "Espresso Machines on a Budget"
    assert result.report.outline == ["Intro", "Top picks", "Verdict"]
    assert result.report.word_count == 1200
    assert result.report.sources == ["https://example.com/review"]


async def test_editor_parse_failure_falls_back_to_raw_report() -> None:
    """元アプリの try/except(構造化レポート不成立なら raw 表示)を踏襲。"""
    raw = "# Just markdown\n\nNo JSON here at all."
    h = make_harness(editor_reply=raw)
    result = await h.run()

    assert result.report.title == TOPIC
    assert result.report.report == raw
    assert result.report.outline == []
    assert result.report.word_count == len(raw.split())


# --- 進捗イベントと実行 API ------------------------------------------------


async def test_progress_events_research_route() -> None:
    h = make_harness()
    await h.run()

    assert [d.handoff_to for d in h.decisions] == ["research"]
    assert h.decisions[0].reason == "product landscape changes quickly"
    assert [(s.stage, s.chars) for s in h.stages] == [
        ("research", len(h.research.reply))
    ]


async def test_progress_events_editor_route() -> None:
    h = make_harness(triage_reply=TRIAGE_EDITOR_JSON)
    await h.run()

    assert [d.handoff_to for d in h.decisions] == ["editor"]
    assert h.stages == []  # research を通らないので StageDone なし


async def test_run_without_stream_returns_output() -> None:
    h = make_harness()
    workflow = build_research_workflow(h.agents, h.fact_store)
    result = await workflow.run(TOPIC)
    outputs = result.get_outputs() if hasattr(result, "get_outputs") else result
    # API 差異に耐える: 何らかの形で ResearchHandoffResult が取れること
    if isinstance(outputs, list):
        assert any(isinstance(o, ResearchHandoffResult) for o in outputs)
    else:
        assert isinstance(outputs, ResearchHandoffResult)


async def test_result_to_dict_is_json_serializable() -> None:
    h = make_harness()
    result = await h.run()

    payload = json.dumps(result.to_dict(), ensure_ascii=False)
    parsed = json.loads(payload)
    assert parsed["handoff_to"] == "research"
    assert parsed["report"]["title"] == "Espresso Machines on a Budget"
    assert parsed["facts"][0]["fact"] == "Machine X costs $450"

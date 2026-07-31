"""リング型ワークフローのオフラインテスト。LLM は scripted fake(ネットワーク
不要)。パターンは ports/research-handoff/tests/test_workflow.py を踏襲。

検証項目(Port 7 の要点 = AG2 Swarm の協調の再現):
- リングの順序: story→gameplay→visuals→tech を 2 周(要約→詳細)
- context への蓄積: 各役割の要約が後続の役割のプロンプトに現れる
  (元アプリの context_variables 相当)
- 動的プロンプト: 1 周目は要約指示、2 周目は '## X Design' セクション指示
  (元アプリの UPDATE_SYSTEM_MESSAGE 相当)
- 最終成果物: 4 セクションの企画書が役割順に組み上がる
  (元アプリの chat_history[-4:] 拾い出し相当)
"""

import json
from dataclasses import dataclass, field

import pytest

pytest.importorskip("agent_framework")

from game_design_team_maf.agents import GameDesignAgents
from game_design_team_maf.prompts import ROLE_ORDER
from game_design_team_maf.spec import GameSpec
from game_design_team_maf.workflow import (
    GameDesignContext,
    GameDesignDocument,
    RoleSectionDone,
    RoleSummaryDone,
    build_game_design_workflow,
)

TASK = GameSpec().to_task()

SUMMARIES = {
    "story": "A frozen kingdom awaits a dragon-riding hero.",
    "gameplay": "Aerial combat plus village rebuilding loops.",
    "visuals": "Painterly realism with aurora-lit skies.",
    "tech": "Unreal Engine 5 targeting PC first.",
}

SECTIONS = {
    "story": "## Story Design\n\nThe kingdom of Everwinter...",
    "gameplay": "## Gameplay Design\n\nCore loop: fly, fight, rebuild...",
    "visuals": "## Visuals Design\n\nPalette of deep blues...",
    "tech": "## Tech Design\n\nUE5 with Nanite...",
}


@dataclass
class FakeResponse:
    text: str


class ScriptedRoleAgent:
    """呼び出しごとに決められた応答を順に返し、受信プロンプトと呼び出し順を
    記録する(1 回目 = 要約、2 回目 = 詳細セクション)。"""

    def __init__(self, role: str, replies: list[str], call_log: list[str]) -> None:
        self.role = role
        self.replies = list(replies)
        self.call_log = call_log
        self.received: list[str] = []

    async def run(self, message: str) -> FakeResponse:
        self.received.append(message)
        self.call_log.append(self.role)
        index = len(self.received) - 1
        assert index < len(self.replies), f"{self.role}: 想定外の {index + 1} 回目の呼び出し"
        return FakeResponse(text=self.replies[index])


@dataclass
class Harness:
    agents: GameDesignAgents
    call_log: list[str]
    results: list[GameDesignDocument] = field(default_factory=list)
    summary_events: list[RoleSummaryDone] = field(default_factory=list)
    section_events: list[RoleSectionDone] = field(default_factory=list)

    def agent(self, role: str) -> ScriptedRoleAgent:
        fake = self.agents.for_role(role)
        assert isinstance(fake, ScriptedRoleAgent)
        return fake

    async def run(self, task: str = TASK) -> GameDesignDocument:
        workflow = build_game_design_workflow(self.agents)
        async for event in workflow.run(GameDesignContext(task=task), stream=True):
            if event.type == "intermediate" and isinstance(event.data, RoleSummaryDone):
                self.summary_events.append(event.data)
            elif event.type == "intermediate" and isinstance(event.data, RoleSectionDone):
                self.section_events.append(event.data)
            elif event.type == "output":
                self.results.append(event.data)
        assert len(self.results) == 1, "最終出力はちょうど 1 回であるべき"
        return self.results[0]


def make_harness() -> Harness:
    call_log: list[str] = []
    fakes = {
        role: ScriptedRoleAgent(role, [SUMMARIES[role], SECTIONS[role]], call_log)
        for role in ROLE_ORDER
    }
    return Harness(agents=GameDesignAgents(**fakes), call_log=call_log)


# --- リングの順序 -----------------------------------------------------------


async def test_ring_runs_two_laps_in_afterwork_order() -> None:
    """story→gameplay→visuals→tech の 2 周(元 AFTER_WORK リング+max_rounds=13
    の 8 エージェントターンに対応)。"""
    h = make_harness()
    await h.run()

    assert h.call_log == list(ROLE_ORDER) + list(ROLE_ORDER)
    for role in ROLE_ORDER:
        assert len(h.agent(role).received) == 2, f"{role} はちょうど 2 回呼ばれるべき"


async def test_task_reaches_every_turn() -> None:
    """元アプリの task(フォーム 15 項目)が全ターンのプロンプトに含まれる。"""
    h = make_harness()
    await h.run()

    for role in ROLE_ORDER:
        for prompt in h.agent(role).received:
            assert "Create a game concept with the following details:" in prompt
            assert "Epic fantasy with dragons" in prompt
            assert "Budget: $10,000" in prompt


# --- context への蓄積(context_variables 相当) -----------------------------


async def test_summary_accumulates_into_later_prompts() -> None:
    """各役割の要約が後続の役割のプロンプトに現れる(共有 context の再現)。"""
    h = make_harness()
    await h.run()

    # 1 周目: gameplay は story の要約を、visuals は story+gameplay を、
    # tech は 3 役割分を受け取る
    gameplay_first = h.agent("gameplay").received[0]
    assert SUMMARIES["story"] in gameplay_first
    assert SUMMARIES["gameplay"] not in gameplay_first

    visuals_first = h.agent("visuals").received[0]
    assert SUMMARIES["story"] in visuals_first
    assert SUMMARIES["gameplay"] in visuals_first

    tech_first = h.agent("tech").received[0]
    for role in ("story", "gameplay", "visuals"):
        assert SUMMARIES[role] in tech_first
    assert SUMMARIES["tech"] not in tech_first


async def test_second_lap_prompts_carry_all_four_summaries() -> None:
    """2 周目(詳細フェーズ)は全役割が 4 つの要約すべてを参照できる。"""
    h = make_harness()
    await h.run()

    for role in ROLE_ORDER:
        second = h.agent(role).received[1]
        for summary in SUMMARIES.values():
            assert summary in second


async def test_context_block_labels_match_original_format() -> None:
    """要約の差し込みは元アプリの `{k.capitalize()} Summary:` 書式。"""
    h = make_harness()
    await h.run()

    tech_first = h.agent("tech").received[0]
    assert "Below are some context for you to refer to:" in tech_first
    assert "Story Summary:" in tech_first
    assert "Gameplay Summary:" in tech_first
    assert "Visuals Summary:" in tech_first
    assert "Tech Summary:" not in tech_first


# --- 動的プロンプト(UPDATE_SYSTEM_MESSAGE 相当) ---------------------------


async def test_first_lap_uses_summary_instruction() -> None:
    h = make_harness()
    await h.run()

    for role in ROLE_ORDER:
        first = h.agent(role).received[0]
        assert f"2-3 sentence summary of your ideas on {role.upper()}" in first
        assert "## " not in first.split("Below are some context")[0], (
            "1 周目にセクション見出し指示が混ざってはいけない"
        )


async def test_second_lap_uses_section_instruction() -> None:
    h = make_harness()
    await h.run()

    for role in ROLE_ORDER:
        second = h.agent(role).received[1]
        assert f"You task is write the {role} part of the report" in second  # 原文の typo 込み
        assert f"Start your response with: '## {role.capitalize()} Design'" in second
        assert "2-3 sentence summary" not in second


# --- 最終成果物(chat_history[-4:] 相当) -----------------------------------


async def test_document_collects_four_sections_in_role_order() -> None:
    h = make_harness()
    doc = await h.run()

    assert doc.sections == SECTIONS
    assert doc.summaries == SUMMARIES
    assert doc.task == TASK


async def test_document_markdown_has_all_headings_in_order() -> None:
    h = make_harness()
    doc = await h.run()

    md = doc.to_markdown()
    positions = [md.index(f"## {role.capitalize()} Design") for role in ROLE_ORDER]
    assert positions == sorted(positions), "セクションは役割順に並ぶべき"
    assert md.startswith("# Game Concept")


async def test_document_to_dict_is_json_serializable() -> None:
    h = make_harness()
    doc = await h.run()

    payload = json.loads(json.dumps(doc.to_dict(), ensure_ascii=False))
    assert payload["sections"]["tech"] == SECTIONS["tech"]
    assert payload["summaries"]["story"] == SUMMARIES["story"]


# --- 進捗イベントと実行 API ------------------------------------------------


async def test_progress_events_follow_ring_order() -> None:
    h = make_harness()
    await h.run()

    assert [e.role for e in h.summary_events] == list(ROLE_ORDER)
    assert [e.summary for e in h.summary_events] == [SUMMARIES[r] for r in ROLE_ORDER]
    assert [e.role for e in h.section_events] == list(ROLE_ORDER)
    assert [e.chars for e in h.section_events] == [len(SECTIONS[r]) for r in ROLE_ORDER]


async def test_run_without_stream_returns_output() -> None:
    h = make_harness()
    workflow = build_game_design_workflow(h.agents)
    result = await workflow.run(GameDesignContext(task=TASK))
    outputs = result.get_outputs() if hasattr(result, "get_outputs") else result
    if isinstance(outputs, list):
        assert any(isinstance(o, GameDesignDocument) for o in outputs)
    else:
        assert isinstance(outputs, GameDesignDocument)


async def test_summary_whitespace_is_stripped() -> None:
    """応答の前後空白は要約・セクションから除去される。"""
    call_log: list[str] = []
    fakes = {
        role: ScriptedRoleAgent(
            role, [f"  {SUMMARIES[role]}  \n", f"\n{SECTIONS[role]}\n  "], call_log
        )
        for role in ROLE_ORDER
    }
    h = Harness(agents=GameDesignAgents(**fakes), call_log=call_log)
    doc = await h.run()

    assert doc.summaries == SUMMARIES
    assert doc.sections == SECTIONS

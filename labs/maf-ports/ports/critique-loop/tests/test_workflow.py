"""ワークフローのオフラインテスト。LLM は scripted fake(ネットワーク不要)。
パターンは ports/mixture-of-agents(fan-out/fan-in)+ ports/game-design-team
(ループエッジ)の tests を踏襲。

検証項目(Port 9 の要点):
- fan-out: 全候補が 1 回ずつ・同一プロンプトで呼ばれる(並列実行の証明つき)
- fan-in: synthesize は全候補の完了後に 1 回だけ呼ばれ、プロンプトに全候補が
  含まれる
- 周回制御: 批評 "accept" で早期終了 / 上限到達で打ち切り(critic の LLM
  呼び出し回数は元実装と同じ = 上限打ち切り時に最終改訂は批評されない)
- 批評の構造化出力パース(ネイティブ .value / JSON テキスト / 壊れた出力の
  安全側フォールバック)
- 改訂プロンプトに批評が含まれること
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest

pytest.importorskip("agent_framework")

from critique_loop_maf.agents import Candidate, CritiqueLoopAgents
from critique_loop_maf.schemas import CritiqueVerdict
from critique_loop_maf.workflow import (
    STOP_ACCEPTED,
    STOP_MAX_ROUNDS,
    CandidateDone,
    CritiqueDecided,
    CritiqueLoopResult,
    DraftSynthesized,
    RevisionDone,
    build_critique_loop_workflow,
)

CANDIDATE_NAMES = ["structured", "practical", "skeptical"]
PROMPT = "Explain recursion with examples."

REVISE_JSON = '{"verdict": "revise", "critiques": ["add complexity analysis", "give an example"]}'
ACCEPT_JSON = '{"verdict": "accept", "critiques": []}'


@dataclass
class FakeResponse:
    text: str
    value: Any = None


class ScriptedAgent:
    """受け取ったメッセージを記録し、決められた応答を順に返す。"""

    def __init__(self, *replies: str | FakeResponse) -> None:
        self.replies = list(replies)
        self.received: list[str] = []

    async def run(self, message: str) -> FakeResponse:
        self.received.append(message)
        if not self.replies:
            raise AssertionError("scripted replies exhausted(想定外の追加呼び出し)")
        reply = self.replies.pop(0)
        return reply if isinstance(reply, FakeResponse) else FakeResponse(text=reply)


@dataclass
class Fakes:
    candidates: dict[str, ScriptedAgent]
    synthesizer: ScriptedAgent
    critic: ScriptedAgent
    reviser: ScriptedAgent
    agents: CritiqueLoopAgents = field(init=False)

    def __post_init__(self) -> None:
        self.agents = CritiqueLoopAgents(
            candidates=[Candidate(name=n, agent=a) for n, a in self.candidates.items()],
            synthesizer=self.synthesizer,
            critic=self.critic,
            reviser=self.reviser,
        )


def make_fakes(critic_replies: list[str | FakeResponse], reviser_count: int = 3) -> Fakes:
    return Fakes(
        candidates={n: ScriptedAgent(f"candidate-answer-from-{n}") for n in CANDIDATE_NAMES},
        synthesizer=ScriptedAgent("synthesized-initial-draft"),
        critic=ScriptedAgent(*critic_replies),
        reviser=ScriptedAgent(*[f"revised-draft-{i + 1}" for i in range(reviser_count)]),
    )


async def run_streaming(workflow) -> tuple[CritiqueLoopResult | None, list[object]]:
    result: CritiqueLoopResult | None = None
    progress: list[object] = []
    async for event in workflow.run(PROMPT, stream=True):
        if event.type == "intermediate":
            progress.append(event.data)
        elif event.type == "output":
            result = event.data
    return result, progress


# --- fan-out / fan-in -------------------------------------------------------


async def test_fan_out_calls_every_candidate_once_with_the_prompt() -> None:
    fakes = make_fakes([ACCEPT_JSON])
    await run_streaming(build_critique_loop_workflow(fakes.agents))

    for name, fake in fakes.candidates.items():
        assert len(fake.received) == 1, f"{name} は 1 回だけ呼ばれるべき"
        assert fake.received[0] == PROMPT


async def test_fan_in_synthesis_prompt_contains_all_candidates() -> None:
    fakes = make_fakes([ACCEPT_JSON])
    await run_streaming(build_critique_loop_workflow(fakes.agents))

    assert len(fakes.synthesizer.received) == 1
    prompt = fakes.synthesizer.received[0]
    # 元アプリの統合プロンプト原文の骨格+全候補の本文
    assert "Synthesize them into ONE best answer" in prompt
    assert "Return the single best final answer." in prompt
    for i, name in enumerate(CANDIDATE_NAMES):
        assert f"candidate-answer-from-{name}" in prompt
        assert f"--- Candidate {i + 1} ---" in prompt


async def test_candidates_run_concurrently() -> None:
    """バリア同期: 全候補が「全員が開始するまで」待つ。逐次実行なら最初の
    1 体がタイムアウトするため、fan-out の並列性が証明される(元アプリの
    ThreadPoolExecutor 相当)。"""
    all_started = asyncio.Event()
    started: set[str] = set()

    class BarrierAgent:
        def __init__(self, name: str) -> None:
            self.name = name

        async def run(self, message: str) -> FakeResponse:
            started.add(self.name)
            if len(started) == len(CANDIDATE_NAMES):
                all_started.set()
            await asyncio.wait_for(all_started.wait(), timeout=5)
            return FakeResponse(text=f"answer-{self.name}")

    agents = CritiqueLoopAgents(
        candidates=[Candidate(name=n, agent=BarrierAgent(n)) for n in CANDIDATE_NAMES],
        synthesizer=ScriptedAgent("draft"),
        critic=ScriptedAgent(ACCEPT_JSON),
        reviser=ScriptedAgent(),
    )
    result, _ = await run_streaming(build_critique_loop_workflow(agents))
    assert isinstance(result, CritiqueLoopResult)
    assert len(result.candidates) == len(CANDIDATE_NAMES)
    # fan-in の並びは到着順でなくエッジ定義順(FanInEdgeRunner の仕様)
    assert [c.name for c in result.candidates] == CANDIDATE_NAMES


# --- 周回制御 ---------------------------------------------------------------


async def test_loop_stops_at_max_rounds_without_final_critique() -> None:
    """批評が revise を出し続けても max_rounds で打ち切る。critic の LLM
    呼び出しは max_rounds 回だけ(元実装が最後の改訂を批評しないのと同じ)。"""
    fakes = make_fakes([REVISE_JSON, REVISE_JSON, REVISE_JSON])
    result, _ = await run_streaming(build_critique_loop_workflow(fakes.agents, max_rounds=2))

    assert isinstance(result, CritiqueLoopResult)
    assert result.stop_reason == STOP_MAX_ROUNDS
    assert len(result.revisions) == 2
    assert len(fakes.critic.received) == 2, "上限到達時は LLM を呼ばず打ち切る"
    assert len(fakes.reviser.received) == 2
    assert result.final_answer == "revised-draft-2"
    assert result.initial_answer == "synthesized-initial-draft"
    assert result.total_iterations == 3  # 元アプリの total_iterations(初稿+改善2)


async def test_early_exit_when_first_critique_accepts() -> None:
    fakes = make_fakes([ACCEPT_JSON])
    result, _ = await run_streaming(build_critique_loop_workflow(fakes.agents, max_rounds=3))

    assert isinstance(result, CritiqueLoopResult)
    assert result.stop_reason == STOP_ACCEPTED
    assert result.revisions == []
    assert result.final_answer == "synthesized-initial-draft"
    assert fakes.reviser.received == []


async def test_accept_after_one_revision() -> None:
    fakes = make_fakes([REVISE_JSON, ACCEPT_JSON])
    result, _ = await run_streaming(build_critique_loop_workflow(fakes.agents, max_rounds=3))

    assert isinstance(result, CritiqueLoopResult)
    assert result.stop_reason == STOP_ACCEPTED
    assert len(result.revisions) == 1
    assert result.final_answer == "revised-draft-1"
    assert result.revisions[0].critiques == ["add complexity analysis", "give an example"]


async def test_max_rounds_validation() -> None:
    fakes = make_fakes([ACCEPT_JSON])
    with pytest.raises(ValueError):
        build_critique_loop_workflow(fakes.agents, max_rounds=0)
    with pytest.raises(ValueError):
        build_critique_loop_workflow(fakes.agents, max_rounds=4)  # 元スライダーは 1-3


def test_empty_candidates_rejected() -> None:
    agents = CritiqueLoopAgents(
        candidates=[],
        synthesizer=ScriptedAgent("draft"),
        critic=ScriptedAgent(ACCEPT_JSON),
        reviser=ScriptedAgent(),
    )
    with pytest.raises(ValueError):
        build_critique_loop_workflow(agents)


# --- 批評の構造化出力とプロンプト伝搬 --------------------------------------


async def test_critique_prompt_contains_question_and_draft() -> None:
    fakes = make_fakes([REVISE_JSON, ACCEPT_JSON])
    await run_streaming(build_critique_loop_workflow(fakes.agents))

    first = fakes.critic.received[0]
    assert f"Original question: {PROMPT}" in first
    assert "synthesized-initial-draft" in first
    assert "Act as a critical reviewer." in first  # 原文の骨格
    # 2 回目の批評は改訂後ドラフトに対して行われる
    assert "revised-draft-1" in fakes.critic.received[1]


async def test_revision_prompt_contains_critiques() -> None:
    """改訂プロンプトに批評が('•' 箇条書きで)含まれる — 元アプリの
    revision_prompt 原文の形。"""
    fakes = make_fakes([REVISE_JSON, ACCEPT_JSON])
    await run_streaming(build_critique_loop_workflow(fakes.agents))

    assert len(fakes.reviser.received) == 1
    prompt = fakes.reviser.received[0]
    assert f"Original question: {PROMPT}" in prompt
    assert "synthesized-initial-draft" in prompt
    assert "• add complexity analysis" in prompt
    assert "• give an example" in prompt
    assert "Revise the original answer to address every critique point." in prompt


async def test_native_structured_output_value_is_preferred() -> None:
    """MAF ネイティブ構造化出力(.value)があればテキストをパースしない。"""
    verdict = CritiqueVerdict(verdict="revise", critiques=["native critique"])
    fakes = make_fakes([FakeResponse(text="(not json)", value=verdict), ACCEPT_JSON])
    result, _ = await run_streaming(build_critique_loop_workflow(fakes.agents))

    assert result is not None
    assert result.revisions[0].critiques == ["native critique"]


async def test_malformed_critique_falls_back_to_revise_with_raw_text() -> None:
    """批評が JSON として壊れていたら、安全側(元実装の無条件改訂に相当)に
    倒して応答全文を 1 批評として改訂する。max_rounds で必ず停止する。"""
    fakes = make_fakes(["the answer lacks examples and depth"])
    result, _ = await run_streaming(build_critique_loop_workflow(fakes.agents, max_rounds=1))

    assert isinstance(result, CritiqueLoopResult)
    assert result.stop_reason == STOP_MAX_ROUNDS
    assert result.revisions[0].critiques == ["the answer lacks examples and depth"]
    assert "• the answer lacks examples and depth" in fakes.reviser.received[0]


async def test_revise_with_empty_critiques_normalized_to_accept() -> None:
    """"revise" なのに批評が空 → 改訂プロンプトに載せるものがないため accept。"""
    fakes = make_fakes(['{"verdict": "revise", "critiques": []}'])
    result, _ = await run_streaming(build_critique_loop_workflow(fakes.agents))

    assert isinstance(result, CritiqueLoopResult)
    assert result.stop_reason == STOP_ACCEPTED
    assert result.revisions == []


# --- 進捗イベントと結果構造 -------------------------------------------------


async def test_progress_event_sequence_for_exhausted_loop() -> None:
    fakes = make_fakes([REVISE_JSON, REVISE_JSON])
    _, progress = await run_streaming(build_critique_loop_workflow(fakes.agents, max_rounds=2))

    candidate_events = [e for e in progress if isinstance(e, CandidateDone)]
    assert sorted(e.name for e in candidate_events) == sorted(CANDIDATE_NAMES)
    assert len([e for e in progress if isinstance(e, DraftSynthesized)]) == 1

    critiques = [e for e in progress if isinstance(e, CritiqueDecided)]
    revisions = [e for e in progress if isinstance(e, RevisionDone)]
    # 批評判断は 3 回(revise ×2 + 上限打ち切り)、改訂は 2 回
    assert [(e.round, e.verdict) for e in critiques] == [
        (1, "revise"),
        (2, "revise"),
        (3, STOP_MAX_ROUNDS),
    ]
    assert [e.round for e in revisions] == [1, 2]


async def test_result_to_dict_round_trips_for_cloud_eval() -> None:
    """to_dict は scripts/run_cloud_eval.py の入力(--save-run JSON)になる。"""
    fakes = make_fakes([REVISE_JSON, ACCEPT_JSON])
    result, _ = await run_streaming(build_critique_loop_workflow(fakes.agents))

    assert result is not None
    data = result.to_dict()
    assert data["prompt"] == PROMPT
    assert data["initial_answer"] == "synthesized-initial-draft"
    assert data["final_answer"] == "revised-draft-1"
    assert data["stop_reason"] == STOP_ACCEPTED
    assert data["total_iterations"] == 2
    assert data["revisions"][0]["round"] == 1
    assert data["revisions"][0]["answer"] == "revised-draft-1"
    assert [c["name"] for c in data["candidates"]] == CANDIDATE_NAMES


async def test_run_without_stream_returns_output() -> None:
    fakes = make_fakes([ACCEPT_JSON])
    workflow = build_critique_loop_workflow(fakes.agents)
    result = await workflow.run(PROMPT)
    outputs = result.get_outputs() if hasattr(result, "get_outputs") else result
    # API 差異に耐える: 何らかの形で CritiqueLoopResult が取れること
    if isinstance(outputs, list):
        assert any(isinstance(o, CritiqueLoopResult) for o in outputs)
    else:
        assert isinstance(outputs, CritiqueLoopResult)

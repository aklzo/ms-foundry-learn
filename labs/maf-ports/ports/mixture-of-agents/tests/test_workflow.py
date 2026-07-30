"""ワークフローのオフラインテスト。LLM は scripted fake(ネットワーク不要)。
パターンは ports/trend-analysis/tests/test_workflow.py の ScriptedAgent を踏襲。

検証項目(Port 2 の要点):
- fan-out: 全 proposer が 1 回ずつ・同一質問で呼ばれる(並列実行の証明つき)
- fan-in: aggregator は全 proposer の完了後に 1 回だけ呼ばれ、プロンプトに
  全回答が含まれる
- 進捗イベント(ProposerDone)と最終出力(MoAResult)の構造
"""

import asyncio
from dataclasses import dataclass

import pytest

pytest.importorskip("agent_framework")

from mixture_of_agents_maf.agents import MoAAgents, Proposer
from mixture_of_agents_maf.workflow import (
    MoAResult,
    ProposerDone,
    ProposerReply,
    build_moa_workflow,
)

PROPOSER_NAMES = ["analyst", "creative", "skeptic", "pragmatist"]
QUESTION = "What are the trade-offs of microservices?"


@dataclass
class FakeResponse:
    text: str


class ScriptedAgent:
    """受け取ったメッセージを記録し、決められた応答を返す。"""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.received: list[str] = []

    async def run(self, message: str) -> FakeResponse:
        self.received.append(message)
        return FakeResponse(text=self.reply)


def make_agents() -> tuple[MoAAgents, dict[str, ScriptedAgent], ScriptedAgent]:
    proposer_fakes = {
        name: ScriptedAgent(f"unique-answer-from-{name}") for name in PROPOSER_NAMES
    }
    aggregator = ScriptedAgent("## Final answer\nSynthesized from all proposers.")
    agents = MoAAgents(
        proposers=[Proposer(name=name, agent=proposer_fakes[name]) for name in PROPOSER_NAMES],
        aggregator=aggregator,
    )
    return agents, proposer_fakes, aggregator


async def run_streaming(workflow) -> tuple[MoAResult | None, list[ProposerDone]]:
    result: MoAResult | None = None
    progress: list[ProposerDone] = []
    async for event in workflow.run(QUESTION, stream=True):
        if event.type == "intermediate" and isinstance(event.data, ProposerDone):
            progress.append(event.data)
        elif event.type == "output":
            result = event.data
    return result, progress


async def test_fan_out_calls_every_proposer_once_with_the_question() -> None:
    agents, proposer_fakes, _ = make_agents()
    await run_streaming(build_moa_workflow(agents))

    for name, fake in proposer_fakes.items():
        assert len(fake.received) == 1, f"{name} は 1 回だけ呼ばれるべき"
        assert QUESTION in fake.received[0]


async def test_fan_in_aggregator_prompt_contains_all_proposals() -> None:
    agents, _, aggregator = make_agents()
    await run_streaming(build_moa_workflow(agents))

    # 全 proposer の完了を待って 1 回だけ呼ばれる
    assert len(aggregator.received) == 1
    prompt = aggregator.received[0]
    # 質問本文と、全 proposer の回答+ラベルが束ねられている
    assert QUESTION in prompt
    for name in PROPOSER_NAMES:
        assert f"unique-answer-from-{name}" in prompt
        assert f"Response from {name}" in prompt


async def test_progress_events_one_per_proposer() -> None:
    agents, proposer_fakes, _ = make_agents()
    _, progress = await run_streaming(build_moa_workflow(agents))

    assert sorted(done.proposer for done in progress) == sorted(PROPOSER_NAMES)
    for done in progress:
        assert done.chars == len(proposer_fakes[done.proposer].reply)


async def test_final_output_structure_and_deterministic_order() -> None:
    agents, _, aggregator = make_agents()
    result, _ = await run_streaming(build_moa_workflow(agents))

    assert isinstance(result, MoAResult)
    assert result.question == QUESTION
    assert result.final_md == aggregator.reply
    # fan-in の並びは到着順でなくエッジ定義順(FanInEdgeRunner の仕様)
    assert [p.proposer for p in result.proposals] == PROPOSER_NAMES
    for proposal in result.proposals:
        assert isinstance(proposal, ProposerReply)
        assert proposal.answer == f"unique-answer-from-{proposal.proposer}"


async def test_proposers_run_concurrently() -> None:
    """バリア同期: 全 proposer が「全員が開始するまで」待つ。逐次実行なら
    最初の 1 体がタイムアウトするため、fan-out の並列性が証明される。"""
    all_started = asyncio.Event()
    started: set[str] = set()

    class BarrierAgent:
        def __init__(self, name: str) -> None:
            self.name = name

        async def run(self, message: str) -> FakeResponse:
            started.add(self.name)
            if len(started) == len(PROPOSER_NAMES):
                all_started.set()
            await asyncio.wait_for(all_started.wait(), timeout=5)
            return FakeResponse(text=f"answer-{self.name}")

    agents = MoAAgents(
        proposers=[Proposer(name=name, agent=BarrierAgent(name)) for name in PROPOSER_NAMES],
        aggregator=ScriptedAgent("final"),
    )
    result, _ = await run_streaming(build_moa_workflow(agents))
    assert isinstance(result, MoAResult)
    assert len(result.proposals) == len(PROPOSER_NAMES)


async def test_run_without_stream_returns_output() -> None:
    agents, *_ = make_agents()
    workflow = build_moa_workflow(agents)
    result = await workflow.run(QUESTION)
    outputs = result.get_outputs() if hasattr(result, "get_outputs") else result
    # API 差異に耐える: 何らかの形で MoAResult が取れること
    if isinstance(outputs, list):
        assert any(isinstance(o, MoAResult) for o in outputs)
    else:
        assert isinstance(outputs, MoAResult)


def test_empty_proposers_rejected() -> None:
    agents = MoAAgents(proposers=[], aggregator=ScriptedAgent("final"))
    with pytest.raises(ValueError):
        build_moa_workflow(agents)

"""「同一質問を N 体へ並列送信 → 全回答を待って統合」を MAF workflow の
ファンアウト/ファンインで表現する。

元アプリは ``asyncio.gather`` で 4 モデルを並列呼び出しし、結果をカンマ結合
してアグリゲータに渡す手続きコードだった。移植では同じ制御フローを
``add_fan_out_edges`` / ``add_fan_in_edges`` のグラフに載せる:

                ┌─▶ Proposer(analyst)   ─┐
    question ──▶ Dispatcher ─▶ Proposer(creative)  ─┼─▶ Aggregator ──▶ MoAResult
                ├─▶ Proposer(skeptic)   ─┤
                └─▶ Proposer(pragmatist)─┘

- fan-out: FanOutEdgeRunner が全 proposer へ同一メッセージを broadcast し、
  内部の ``asyncio.gather`` で並列実行する。
- fan-in: FanInEdgeRunner がソース毎に回答をバッファし、**全 proposer の
  完了を待って** ``list[ProposerReply]`` を 1 回だけ aggregator に配送する
  (並び順は到着順でなくエッジ定義順 = 決定的)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Never

from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler

from .agents import MoAAgents, Proposer

# --- グラフを流れるメッセージ ---------------------------------------------


@dataclass
class ProposalRequest:
    """dispatcher → 各 proposer(fan-out で全員に同一内容が届く)。"""

    question: str


@dataclass
class ProposerReply:
    """proposer → aggregator(fan-in で list に束ねられる)。"""

    question: str
    proposer: str
    answer: str


@dataclass
class ProposerDone:
    """進捗イベント(intermediate output)。"""

    proposer: str
    chars: int


@dataclass
class MoAResult:
    """最終成果物。個別回答(元アプリの expander 相当)も保持する。"""

    question: str
    proposals: list[ProposerReply]
    final_md: str


# --- Executors -------------------------------------------------------------


class DispatcherExecutor(Executor):
    """str 入力を ProposalRequest に持ち上げてファンアウトの起点になる。"""

    def __init__(self) -> None:
        super().__init__(id="dispatcher")

    @handler
    async def dispatch(self, question: str, ctx: WorkflowContext[ProposalRequest]) -> None:
        await ctx.send_message(ProposalRequest(question=question))


class ProposerExecutor(Executor):
    def __init__(self, proposer: Proposer) -> None:
        super().__init__(id=f"proposer_{proposer.name}")
        self._proposer = proposer

    @handler
    async def propose(
        self, request: ProposalRequest, ctx: WorkflowContext[ProposerReply, ProposerDone]
    ) -> None:
        response = await self._proposer.agent.run(request.question)
        answer = response.text
        await ctx.yield_output(ProposerDone(proposer=self._proposer.name, chars=len(answer)))
        await ctx.send_message(
            ProposerReply(
                question=request.question,
                proposer=self._proposer.name,
                answer=answer,
            )
        )


class AggregatorExecutor(Executor):
    """fan-in の合流点。全 proposer の回答 list を 1 プロンプトに束ねて統合する。"""

    def __init__(self, agents: MoAAgents) -> None:
        super().__init__(id="aggregator")
        self._agents = agents

    @handler
    async def aggregate(
        self, replies: list[ProposerReply], ctx: WorkflowContext[Never, MoAResult]
    ) -> None:
        question = replies[0].question
        # 元アプリはカンマ結合のみ・質問本文もアグリゲータに渡していなかった。
        # 移植では回答をラベル付きセクションにし、質問本文も渡す(README 参照)。
        sections = "\n\n".join(
            f"### Response from {reply.proposer}\n{reply.answer}" for reply in replies
        )
        prompt = f"User question:\n{question}\n\nResponses from models:\n\n{sections}"
        response = await self._agents.aggregator.run(prompt)
        await ctx.yield_output(
            MoAResult(
                question=question,
                proposals=list(replies),
                final_md=response.text,
            )
        )


# --- 組み立て ---------------------------------------------------------------


def build_moa_workflow(agents: MoAAgents):
    """``await workflow.run(question)`` で実行する単発ワークフローを組み立てる。
    進捗(各 proposer の完了)は ``workflow.run(question, stream=True)`` の
    intermediate イベント。"""
    if not agents.proposers:
        raise ValueError("proposer が 0 体です(FOUNDRY_PROPOSER_MODELS を確認)")

    dispatcher = DispatcherExecutor()
    proposers = [ProposerExecutor(proposer) for proposer in agents.proposers]
    aggregator = AggregatorExecutor(agents)

    return (
        WorkflowBuilder(
            start_executor=dispatcher,
            output_from=[aggregator],
            intermediate_output_from=list(proposers),
        )
        .add_fan_out_edges(dispatcher, proposers)
        .add_fan_in_edges(proposers, aggregator)
        .build()
    )

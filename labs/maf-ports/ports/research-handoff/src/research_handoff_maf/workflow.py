"""handoff(triage → research / editor)を「構造化出力によるルーティング判断+
switch-case エッジ」で表現する。

元アプリは OpenAI Agents SDK の ``handoffs=[handoff(research), handoff(editor)]``
で LLM 自身に委譲先を選ばせ(SDK が handoff ツールを自動生成)、editor への
2 段目は ``Runner.run(editor, triage_result.to_input_list())`` と手続きで呼んで
いた。移植では委譲判断を ``TriageDecision.handoff_to`` というデータに落とし、
グラフのエッジ条件で分岐させる:

                      ┌─[handoff_to == "research"]─▶ Research ──▶ Editor ─▶ 結果
    topic ─▶ Triage ──┤   (search_web +                (research 要約+facts を
                      │    save_important_fact)         プロンプトで受領)
                      └─[Default("editor" 直行)]──────▶ Editor ─▶ 結果

- MAF core 1.10/1.12 に handoff の first-class API はない(別パッケージ
  agent-framework-orchestrations の HandoffBuilder。調査結果と不採用理由は
  README)。ここでは core の ``add_switch_case_edge_group`` を使う。
- 「handoff 先が何を受け取るか」(元 SDK では会話履歴が暗黙に引き継がれる)
  は、本移植では型付きメッセージ(TriageOutcome / ResearchFindings)として
  明示する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Never

from agent_framework import Case, Default, Executor, WorkflowBuilder, WorkflowContext, handler

from .agents import ResearchHandoffAgents
from .schemas import (
    ResearchPlan,
    ResearchReport,
    SchemaError,
    TriageDecision,
    parse_structured,
)
from .tools import FactStore, SavedFact

# --- グラフを流れるメッセージ ---------------------------------------------


@dataclass
class TriageOutcome:
    """triage → research(または editor 直行)。委譲判断+計画。"""

    topic: str
    plan: ResearchPlan
    handoff_to: str  # "research" | "editor"
    reason: str
    fallback: bool = False  # 構造化出力のパースに失敗し既定計画で続行したか


@dataclass
class ResearchFindings:
    """research → editor。要約と保存済みファクト。"""

    outcome: TriageOutcome
    summary_md: str
    facts: list[SavedFact] = field(default_factory=list)


@dataclass
class HandoffDecided:
    """進捗イベント(triage の委譲判断)。"""

    handoff_to: str
    reason: str


@dataclass
class StageDone:
    """進捗イベント(research 完了)。"""

    stage: str
    chars: int


@dataclass
class ResearchHandoffResult:
    """最終成果物。"""

    topic: str
    handoff_to: str
    reason: str
    plan: ResearchPlan
    research_md: str | None  # editor 直行時は None
    facts: list[SavedFact]
    report: ResearchReport

    def to_dict(self) -> dict[str, Any]:
        """CLI ``--json`` 用(Pydantic フィールドを含むため asdict でなく手動)。"""
        from dataclasses import asdict

        return {
            "topic": self.topic,
            "handoff_to": self.handoff_to,
            "reason": self.reason,
            "plan": self.plan.model_dump(),
            "research_md": self.research_md,
            "facts": [asdict(f) for f in self.facts],
            "report": self.report.model_dump(),
        }


# --- Executors -------------------------------------------------------------


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) or "- (none)"


class TriageExecutor(Executor):
    """計画+委譲判断を構造化出力で得る(元の triage_agent 相当)。"""

    def __init__(self, agents: ResearchHandoffAgents) -> None:
        super().__init__(id="triage")
        self._agents = agents

    @handler
    async def triage(
        self, topic: str, ctx: WorkflowContext[TriageOutcome, HandoffDecided]
    ) -> None:
        # 実行プロンプトは元アプリの Runner.run(triage_agent, ...) の原文。
        response = await self._agents.triage.run(
            f"Research this topic thoroughly: {topic}. This research will be used to "
            "create a comprehensive research report."
        )
        try:
            decision = parse_structured(response, TriageDecision)
            outcome = TriageOutcome(
                topic=topic,
                plan=decision.plan,
                handoff_to=decision.handoff_to,
                reason=decision.reason,
            )
        except SchemaError:
            # 元アプリの fallback(final_output が ResearchPlan でなければ既定
            # 計画で続行)を踏襲。委譲先は安全側の research に倒す。
            outcome = TriageOutcome(
                topic=topic,
                plan=ResearchPlan(
                    topic=topic,
                    search_queries=[f"Researching {topic}"],
                    focus_areas=[f"General information about {topic}"],
                ),
                handoff_to="research",
                reason="fallback: triage output was not parseable",
                fallback=True,
            )
        await ctx.yield_output(
            HandoffDecided(handoff_to=outcome.handoff_to, reason=outcome.reason)
        )
        await ctx.send_message(outcome)


class ResearchExecutor(Executor):
    """計画のクエリを検索し要約を作る(元の research_agent 相当)。

    元 SDK の handoff では「会話履歴の全体」が暗黙に引き継がれた。ここでは
    handoff 先が受け取るコンテキスト(計画のクエリと focus areas)を
    プロンプトとして明示的に組み立てる。
    """

    def __init__(self, agents: ResearchHandoffAgents, fact_store: FactStore) -> None:
        super().__init__(id="research")
        self._agents = agents
        self._fact_store = fact_store

    @handler
    async def research(
        self, outcome: TriageOutcome, ctx: WorkflowContext[ResearchFindings, StageDone]
    ) -> None:
        self._fact_store.clear()
        plan = outcome.plan
        prompt = (
            f"Research topic: {plan.topic}\n\n"
            f"Focus areas:\n{_bullets(plan.focus_areas)}\n\n"
            "Run each of these search queries with the search_web tool and summarize "
            f"what you find:\n{_bullets(plan.search_queries)}\n\n"
            "Save the most important facts with save_important_fact as you go."
        )
        response = await self._agents.research.run(prompt)
        summary = response.text
        await ctx.yield_output(StageDone(stage="research", chars=len(summary)))
        await ctx.send_message(
            ResearchFindings(
                outcome=outcome,
                summary_md=summary,
                facts=self._fact_store.snapshot(),
            )
        )


class EditorExecutor(Executor):
    """最終レポートを構造化出力で書く(元の editor_agent 相当)。

    2 つの handler を持ち、research 経由(ResearchFindings)と triage からの
    直行(TriageOutcome)のどちらの経路でも受けられる。
    """

    def __init__(self, agents: ResearchHandoffAgents) -> None:
        super().__init__(id="editor")
        self._agents = agents

    @handler
    async def edit_researched(
        self, findings: ResearchFindings, ctx: WorkflowContext[Never, ResearchHandoffResult]
    ) -> None:
        outcome = findings.outcome
        facts_md = (
            "\n".join(f"- {f.fact} (source: {f.source})" for f in findings.facts)
            or "- (no facts were saved)"
        )
        prompt = (
            f"Original query: {outcome.topic}\n\n"
            f"Research plan focus areas:\n{_bullets(outcome.plan.focus_areas)}\n\n"
            f"Initial research by the research assistant:\n\n{findings.summary_md}\n\n"
            f"Important facts saved during research:\n{facts_md}\n\n"
            "Write the comprehensive report now."
        )
        report = await self._write_report(prompt, outcome.topic)
        await ctx.yield_output(
            ResearchHandoffResult(
                topic=outcome.topic,
                handoff_to=outcome.handoff_to,
                reason=outcome.reason,
                plan=outcome.plan,
                research_md=findings.summary_md,
                facts=findings.facts,
                report=report,
            )
        )

    @handler
    async def edit_direct(
        self, outcome: TriageOutcome, ctx: WorkflowContext[Never, ResearchHandoffResult]
    ) -> None:
        prompt = (
            f"Original query: {outcome.topic}\n\n"
            f"Research plan focus areas:\n{_bullets(outcome.plan.focus_areas)}\n\n"
            "No web research was performed for this query; the triage agent judged it "
            "answerable from established knowledge. Write the report from established "
            "knowledge, and avoid claims that would require up-to-date sources.\n\n"
            "Write the comprehensive report now."
        )
        report = await self._write_report(prompt, outcome.topic)
        await ctx.yield_output(
            ResearchHandoffResult(
                topic=outcome.topic,
                handoff_to=outcome.handoff_to,
                reason=outcome.reason,
                plan=outcome.plan,
                research_md=None,
                facts=[],
                report=report,
            )
        )

    async def _write_report(self, prompt: str, topic: str) -> ResearchReport:
        response = await self._agents.editor.run(prompt)
        try:
            return parse_structured(response, ResearchReport)
        except SchemaError:
            # 元アプリの try/except(構造化レポートが得られなければ raw を
            # 表示)を踏襲し、生テキストをそのままレポート本文にする。
            text = response.text
            return ResearchReport(
                title=topic,
                outline=[],
                report=text,
                sources=[],
                word_count=len(text.split()),
            )


# --- 組み立て ---------------------------------------------------------------


def build_research_workflow(agents: ResearchHandoffAgents, fact_store: FactStore):
    """``await workflow.run(topic)`` で実行する単発ワークフローを組み立てる。
    進捗は ``workflow.run(topic, stream=True)`` の intermediate イベント
    (HandoffDecided / StageDone)。"""
    triage = TriageExecutor(agents)
    research = ResearchExecutor(agents, fact_store)
    editor = EditorExecutor(agents)

    return (
        WorkflowBuilder(
            start_executor=triage,
            output_from=[editor],
            intermediate_output_from=[triage, research],
        )
        .add_switch_case_edge_group(
            triage,
            [
                Case(
                    condition=lambda outcome: getattr(outcome, "handoff_to", None)
                    == "research",
                    target=research,
                ),
                Default(target=editor),
            ],
        )
        .add_edge(research, editor)
        .build()
    )

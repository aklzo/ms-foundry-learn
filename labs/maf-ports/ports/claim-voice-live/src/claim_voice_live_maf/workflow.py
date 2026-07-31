"""FNOL コア: 抽出 → 検証 → 分類 → 規則 → チェックリスト → ゲート → パケット
の直列 7 段を MAF workflow で表現する(音声にもテキスト UI にも依存しない)。

元 ADK ``SequentialAgent``(agent.py の create_workflow)との対応:

    NormalizeClaimNarrative   (LlmAgent)      → ExtractExecutor   (LLM)
    ValidateRequiredClaimFields (FunctionNode) → ValidateExecutor  (決定論)
    ClassifyClaimTypeAndSeverity (LlmAgent)    → ClassifyExecutor  (LLM)
    ApplyCoverageAndEvidenceRules (FunctionNode) → RulesExecutor   (決定論)
    GenerateDocumentChecklist (FunctionNode)   → ChecklistExecutor (決定論)
    FraudSignalAndSafetyGate (FunctionNode)    → GateExecutor      (決定論)
    FinalClaimIntakePacket (FunctionNode)      → PacketExecutor    (決定論・最終出力)

元は毎ターン「請求者発話の全文」をグラフに流して状態を作り直す設計
(run_claim_workflow)で、それをそのまま踏襲する — パケットの「漸進構築」は
ターンごとに transcript が伸びることで実現される(conversation.py)。

段間のメッセージは単一の ``IntakeDraft`` を埋めながら運ぶ(直列 7 段に段ごとの
型を用意する冗長さより、必須フィールドの存在アサーションを選んだ)。抽出/分類の
構造化出力が壊れた場合は空クレーム/初期分類へフォールバックし、決定論段が
「missing だらけの状態」として処理を続行する(会話が止まらないことを優先)。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Never

from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler

from .agents import ClaimIntakeAgents, SupportsRun
from .policies import (
    apply_coverage_and_evidence_rules,
    build_claim_intake_packet,
    build_intake_state,
    fraud_signal_and_safety_gate,
    generate_document_checklist,
    validate_required_claim_fields,
)
from .schemas import (
    ClaimClassification,
    ClaimNarrative,
    CoverageEvidenceDecision,
    DocumentChecklist,
    FieldValidation,
    FraudSafetyGate,
    IntakeState,
    SchemaError,
    parse_structured,
)

# --- グラフを流れるメッセージ ---------------------------------------------


@dataclass
class ClaimTurn:
    """ワークフロー入力: ここまでの請求者発話の全文(元 run_claim_workflow の引数)。"""

    transcript: str


@dataclass
class IntakeDraft:
    """段を経るごとに埋まっていく中間状態。"""

    transcript: str
    claim: ClaimNarrative
    validation: FieldValidation | None = None
    classification: ClaimClassification | None = None
    coverage: CoverageEvidenceDecision | None = None
    checklist: DocumentChecklist | None = None
    gate: FraudSafetyGate | None = None
    #: 抽出/分類のフォールバックが起きた場合の注記(パケットには載せない)
    degradations: list[str] = field(default_factory=list)


@dataclass
class StageDone:
    """進捗イベント(intermediate output)。元 ADK の FunctionNode summary に対応。"""

    stage: str
    summary: str


# --- Executors -------------------------------------------------------------

#: 元 run_claim_workflow が ADK へ投げていた実行プロンプト(原文)。
EXTRACT_PROMPT_PREFIX = (
    "Use this full claimant transcript as the source of truth for "
    "the insurance intake workflow. Do not invent missing facts.\n\n"
)


class ExtractExecutor(Executor):
    """請求者発話の全文から ClaimNarrative を構造化抽出する(LLM 段)。"""

    def __init__(self, agent: SupportsRun) -> None:
        super().__init__(id="extract")
        self._agent = agent

    @handler
    async def extract(self, turn: ClaimTurn, ctx: WorkflowContext[IntakeDraft, StageDone]) -> None:
        degradations: list[str] = []
        response = await self._agent.run(EXTRACT_PROMPT_PREFIX + turn.transcript)
        try:
            claim = parse_structured(response, ClaimNarrative)
        except SchemaError as exc:
            claim = ClaimNarrative()
            degradations.append(f"extraction fallback to blank claim: {exc}")
        await ctx.yield_output(StageDone(stage="extract", summary="claim fields extracted"))
        await ctx.send_message(
            IntakeDraft(transcript=turn.transcript, claim=claim, degradations=degradations)
        )


class ValidateExecutor(Executor):
    """必須項目の決定論バリデーション。"""

    def __init__(self) -> None:
        super().__init__(id="validate")

    @handler
    async def validate(self, draft: IntakeDraft, ctx: WorkflowContext[IntakeDraft, StageDone]) -> None:
        draft.validation = validate_required_claim_fields(draft.claim)
        await ctx.yield_output(
            StageDone(stage="validate", summary=f"missing={len(draft.validation.missing_fields)}")
        )
        await ctx.send_message(draft)


class ClassifyExecutor(Executor):
    """クレーム種別・重大度の分類(LLM 段)。前段の結果を JSON でプロンプトに渡す。"""

    def __init__(self, agent: SupportsRun) -> None:
        super().__init__(id="classify")
        self._agent = agent

    @handler
    async def classify(self, draft: IntakeDraft, ctx: WorkflowContext[IntakeDraft, StageDone]) -> None:
        assert draft.validation is not None
        prompt = (
            "Normalized claim:\n"
            f"{json.dumps(draft.claim.model_dump(exclude_none=True), ensure_ascii=False)}\n\n"
            "Validation:\n"
            f"{json.dumps(draft.validation.model_dump(exclude_none=True), ensure_ascii=False)}"
        )
        response = await self._agent.run(prompt)
        try:
            draft.classification = parse_structured(response, ClaimClassification)
        except SchemaError as exc:
            draft.classification = ClaimClassification()
            draft.degradations.append(f"classification fallback to initial: {exc}")
        await ctx.yield_output(
            StageDone(
                stage="classify",
                summary=f"{draft.classification.claim_type}/{draft.classification.severity}",
            )
        )
        await ctx.send_message(draft)


class RulesExecutor(Executor):
    """カバレッジ・証憑・一次ルーティング規則(決定論)。"""

    def __init__(self) -> None:
        super().__init__(id="rules")

    @handler
    async def apply(self, draft: IntakeDraft, ctx: WorkflowContext[IntakeDraft, StageDone]) -> None:
        assert draft.validation is not None and draft.classification is not None
        draft.coverage = apply_coverage_and_evidence_rules(
            draft.claim, draft.validation, draft.classification
        )
        await ctx.yield_output(
            StageDone(stage="rules", summary=f"route={draft.coverage.routing_decision}")
        )
        await ctx.send_message(draft)


class ChecklistExecutor(Executor):
    """請求者向け書類チェックリスト生成(決定論)。"""

    def __init__(self) -> None:
        super().__init__(id="checklist")

    @handler
    async def build(self, draft: IntakeDraft, ctx: WorkflowContext[IntakeDraft, StageDone]) -> None:
        assert draft.classification is not None and draft.coverage is not None
        draft.checklist = generate_document_checklist(
            draft.claim, draft.classification, draft.coverage
        )
        await ctx.yield_output(
            StageDone(stage="checklist", summary=f"items={len(draft.checklist.items)}")
        )
        await ctx.send_message(draft)


class GateExecutor(Executor):
    """不正・タイミング・安全ゲート(決定論)。最終ルートを決める。"""

    def __init__(self) -> None:
        super().__init__(id="gate")

    @handler
    async def gate(self, draft: IntakeDraft, ctx: WorkflowContext[IntakeDraft, StageDone]) -> None:
        assert (
            draft.validation is not None
            and draft.classification is not None
            and draft.coverage is not None
        )
        draft.gate = fraud_signal_and_safety_gate(
            draft.claim, draft.validation, draft.classification, draft.coverage
        )
        await ctx.yield_output(
            StageDone(stage="gate", summary=f"final_route={draft.gate.final_routing_decision}")
        )
        await ctx.send_message(draft)


class PacketExecutor(Executor):
    """最終 FNOL パケットを組み立て、IntakeState を出力する。"""

    def __init__(self) -> None:
        super().__init__(id="packet")

    @handler
    async def build(self, draft: IntakeDraft, ctx: WorkflowContext[Never, IntakeState]) -> None:
        assert (
            draft.validation is not None
            and draft.classification is not None
            and draft.coverage is not None
            and draft.checklist is not None
            and draft.gate is not None
        )
        packet = build_claim_intake_packet(
            draft.claim,
            draft.validation,
            draft.classification,
            draft.coverage,
            draft.checklist,
            draft.gate,
        )
        await ctx.yield_output(
            IntakeState(
                claim=draft.claim,
                validation=draft.validation,
                classification=draft.classification,
                coverage=draft.coverage,
                checklist=draft.checklist,
                gate=draft.gate,
                packet=packet,
            )
        )


# --- 組み立て・実行 ---------------------------------------------------------


def build_intake_workflow(agents: ClaimIntakeAgents):
    """``await workflow.run(ClaimTurn(...))`` で 1 ターン分を実行するワークフロー。"""
    extract = ExtractExecutor(agents.extractor)
    validate = ValidateExecutor()
    classify = ClassifyExecutor(agents.classifier)
    rules = RulesExecutor()
    checklist = ChecklistExecutor()
    gate = GateExecutor()
    packet = PacketExecutor()

    return (
        WorkflowBuilder(
            start_executor=extract,
            output_from=[packet],
            intermediate_output_from=[extract, validate, classify, rules, checklist, gate],
        )
        .add_edge(extract, validate)
        .add_edge(validate, classify)
        .add_edge(classify, rules)
        .add_edge(rules, checklist)
        .add_edge(checklist, gate)
        .add_edge(gate, packet)
        .build()
    )


async def run_intake_turn(
    agents: ClaimIntakeAgents,
    transcript: str,
    on_stage=None,
) -> IntakeState:
    """1 ターン分のワークフロー実行(元 run_claim_workflow に対応)。

    transcript が空なら LLM を呼ばず初期状態を返す(元実装と同じ短絡)。
    ``on_stage`` に callable を渡すと StageDone 進捗を受け取れる。
    """
    text = (transcript or "").strip()
    if not text:
        return build_intake_state()

    workflow = build_intake_workflow(agents)
    state: IntakeState | None = None
    async for event in workflow.run(ClaimTurn(transcript=text), stream=True):
        if event.type == "intermediate" and isinstance(event.data, StageDone):
            if on_stage is not None:
                on_stage(event.data)
        elif event.type == "output" and isinstance(event.data, IntakeState):
            state = event.data
    if state is None:
        raise RuntimeError("intake workflow produced no IntakeState")
    return state

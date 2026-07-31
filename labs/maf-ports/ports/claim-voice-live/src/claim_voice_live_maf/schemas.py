"""FNOL(First Notice of Loss)ワークフローの構造化データ契約。

元アプリ schemas.py の Pydantic モデルをほぼそのまま移植。差分は 2 点:

1. ``ClaimNarrative`` / ``ClaimClassification`` に既定値を与えた。元は
   ``blank_claim()`` / ``initial_classification()`` という dict ファクトリで
   「空のクレーム」を表現していたが、移植では ``ClaimNarrative()`` /
   ``ClaimClassification()`` がそのまま空状態になる(漸進構築の起点)。
2. ``IntakeState``(全段の成果物を束ねるスナップショット)を追加。元 ADK は
   session.state の無型 dict にキー 7 個で持っていたものを 1 モデルに固めた。

``parse_structured`` / ``extract_json`` は research-handoff / agentic-search-maf
の lenient パーサをコピー(構造化出力を無視するモデルへのフォールバック)。
"""

from __future__ import annotations

import contextlib
import json
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

ClaimType = Literal[
    "home_water_damage",
    "auto_collision",
    "theft_property_loss",
    "health_medical_reimbursement",
    "travel_delay_cancellation",
    "other",
]

Severity = Literal["low", "medium", "high", "urgent"]
IntakeStatus = Literal["valid", "missing_info"]
RoutingDecision = Literal[
    "ready_for_adjuster",
    "needs_docs",
    "special_investigation",
    "emergency_escalation",
]

#: 元アプリの「未指定」マーカー(policies の _blank 判定と対)
NOT_SPECIFIED = "not specified"


class ClaimNarrative(BaseModel):
    """乱雑なクレーム語りから正規化した事実(元 blank_claim() が既定値)。"""

    policyholder_name: str = Field(
        default=NOT_SPECIFIED, description="Name of the policyholder or claimant."
    )
    policy_number: str = Field(
        default=NOT_SPECIFIED, description="Policy or member number if supplied."
    )
    contact_method: str = Field(
        default=NOT_SPECIFIED, description="Best available phone, email, or mailing contact."
    )
    date_of_loss: str = Field(
        default=NOT_SPECIFIED, description="Date or date range when the loss occurred."
    )
    reported_date: str = Field(
        default=NOT_SPECIFIED,
        description="Date the claimant says they are reporting, if supplied.",
    )
    loss_location: str = Field(
        default=NOT_SPECIFIED,
        description="City, address, intersection, facility, or travel route.",
    )
    loss_description: str = Field(
        default=NOT_SPECIFIED, description="Plain-language description of what happened."
    )
    estimated_loss_usd: float | None = Field(
        default=None, description="Estimated financial loss in USD when supplied."
    )
    injuries_or_safety_concerns: list[str] = Field(default_factory=list)
    parties_involved: list[str] = Field(default_factory=list)
    evidence_available: list[str] = Field(default_factory=list)
    documents_mentioned: list[str] = Field(default_factory=list)
    missing_or_uncertain_facts: list[str] = Field(default_factory=list)
    raw_narrative_summary: str = Field(
        default=NOT_SPECIFIED, description="Short factual summary of the source narrative."
    )
    assumptions: list[str] = Field(default_factory=list)


class FieldValidation(BaseModel):
    """必須インテーク項目の決定論バリデーション。"""

    intake_status: IntakeStatus
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    ready_for_policy_review: bool


class ClaimClassification(BaseModel):
    """LLM によるクレーム種別・運用重大度の分類(既定値 = 元 initial_classification())。"""

    claim_type: ClaimType = "other"
    severity: Severity = "medium"
    severity_rationale: str = "Waiting for claimant facts."
    likely_policy_line: str = "unknown"
    loss_drivers: list[str] = Field(default_factory=list)
    claimant_needs: list[str] = Field(default_factory=lambda: ["Provide initial loss facts."])


class EvidenceRuleFinding(BaseModel):
    """カバレッジ/証憑/ルーティング規則が生成する決定論所見。"""

    rule_id: str
    severity: Severity
    message: str
    required_action: Literal[
        "collect_info",
        "collect_document",
        "adjuster_review",
        "siu_review",
        "emergency_escalation",
    ]
    document: str | None = None


class CoverageEvidenceDecision(BaseModel):
    """カバレッジ・証憑ゲート後の決定論ルーティング。"""

    routing_decision: RoutingDecision
    provisional_coverage_considerations: list[str] = Field(default_factory=list)
    required_documents: list[str] = Field(default_factory=list)
    findings: list[EvidenceRuleFinding] = Field(default_factory=list)
    audit_trail: list[str] = Field(default_factory=list)


class DocumentChecklistItem(BaseModel):
    """請求者向けチェックリスト 1 項目。"""

    item: str
    reason: str
    priority: Literal["required", "recommended", "conditional"]
    already_provided: bool = False


class DocumentChecklist(BaseModel):
    """クレームパケット用の書類チェックリスト。"""

    items: list[DocumentChecklistItem] = Field(default_factory=list)
    claimant_tip: str


class FraudSafetySignal(BaseModel):
    """SIU / 不正パターン / 安全性の決定論シグナル。"""

    signal_id: str
    severity: Severity
    message: str
    route_to_siu: bool = False
    route_to_emergency: bool = False


class FraudSafetyGate(BaseModel):
    """最終の決定論的安全・不正ルーティングゲート。"""

    final_routing_decision: RoutingDecision
    signals: list[FraudSafetySignal] = Field(default_factory=list)
    audit_trail: list[str] = Field(default_factory=list)


class ClaimIntakePacket(BaseModel):
    """最終の FNOL パケット(元は ADK Web へ返す Markdown 付きモデル)。"""

    claim_type: ClaimType
    intake_status: IntakeStatus
    severity: Severity
    routing_decision: RoutingDecision
    missing_information: list[str] = Field(default_factory=list)
    required_documents: list[DocumentChecklistItem] = Field(default_factory=list)
    coverage_considerations: list[str] = Field(default_factory=list)
    adjuster_handoff_summary: str
    claimant_next_message: str
    audit_trail: list[str] = Field(default_factory=list)
    markdown: str


class IntakeState(BaseModel):
    """1 ターン分のワークフロー実行後の全成果物スナップショット。

    元 ADK の session.state(normalized_claim / field_validation / ... の
    無型 dict 7 キー)に対応する型付き版。テキスト対話層・Voice Live 層の
    両方がこの 1 モデルだけを見る。
    """

    claim: ClaimNarrative
    validation: FieldValidation
    classification: ClaimClassification
    coverage: CoverageEvidenceDecision
    checklist: DocumentChecklist
    gate: FraudSafetyGate
    packet: ClaimIntakePacket

    @property
    def route(self) -> RoutingDecision:
        return self.gate.final_routing_decision

    @property
    def next_question(self) -> str:
        return self.packet.claimant_next_message

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


# --- lenient 構造化出力パーサ(research-handoff から移植)---------------------


class SchemaError(RuntimeError):
    """構造化出力が期待スキーマとして解釈できない。"""


def parse_structured(response: Any, model: type[BaseModel]) -> Any:
    """MAF エージェント応答を ``model`` として解釈する。

    ネイティブ構造化出力(``response.value``)を優先し、response_format を
    無視するプロバイダや JSON を散文で包むモデルには生テキストからの lenient
    抽出でフォールバックする。
    """
    value = None
    with contextlib.suppress(Exception):
        value = getattr(response, "value", None)
    if isinstance(value, model):
        return value
    try:
        return model.model_validate(extract_json(response.text))
    except ValidationError as exc:
        raise SchemaError(f"response does not match {model.__name__}: {exc}") from exc


def extract_json(text: str) -> Any:
    """LLM 出力から最初の JSON オブジェクト/配列を取り出す。"""
    try:
        return json.loads(text.strip())
    except (json.JSONDecodeError, ValueError):
        pass
    candidate = _balanced_json_slice(text)
    if candidate is None:
        raise SchemaError(f"no JSON found in: {_preview(text)}")
    try:
        return json.loads(candidate)
    except (json.JSONDecodeError, ValueError) as exc:
        raise SchemaError(f"invalid JSON ({exc}): {_preview(candidate)}") from exc


def _balanced_json_slice(text: str) -> str | None:
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        return None
    start = min(starts)
    open_char = text[start]
    close_char = "}" if open_char == "{" else "]"

    depth = 0
    in_string = False
    escaped = False
    for offset, char in enumerate(text[start:]):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return text[start : start + offset + 1]
    return None


def _preview(text: str) -> str:
    return text.strip()[:200]

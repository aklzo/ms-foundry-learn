"""LLM 2 段(申請の構造化・検査)の構造化出力スキーマ。

元 trust_gated_agent_team の 3 段(Researcher → Analyst → Writer)は自由文
リレーだったが、移植では段間を型で繋ぎ、信頼スコアを「段の出力の決定論検査」
から導けるようにした(trust.py)。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

NOT_SPECIFIED = "not specified"

ExpenseCategory = Literal["travel", "meals", "equipment", "software", "training", "other"]


class ExpenseClaim(BaseModel):
    """申請段(intake)の出力: 自由文の経費申請を構造化したもの。"""

    employee_id: str = NOT_SPECIFIED
    employee_name: str = NOT_SPECIFIED
    department: str = NOT_SPECIFIED
    amount_usd: float | None = None
    category: ExpenseCategory = "other"
    expense_date: str = NOT_SPECIFIED
    description: str = ""
    has_receipt: bool = False
    receipt_reference: str = NOT_SPECIFIED
    missing_or_uncertain: list[str] = Field(default_factory=list)


class InspectionFinding(BaseModel):
    finding_id: str  # 例: INS-001
    severity: Literal["info", "warning", "critical"]
    note: str


class InspectionReport(BaseModel):
    """検査段(inspector)の出力。confidence と findings は信頼スコアの入力になる。"""

    summary: str
    findings: list[InspectionFinding] = Field(default_factory=list)
    recommendation: Literal["approve", "reject", "needs_information"]
    confidence: float = Field(ge=0.0, le=1.0)

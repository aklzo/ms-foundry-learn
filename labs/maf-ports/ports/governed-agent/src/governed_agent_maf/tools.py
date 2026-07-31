"""承認エージェントに渡す経費精算ツール群(クロージャで台帳を捕捉)。

``delete_expense_record`` はポリシーの許可リストに**載っていない**ツール。
本来は least privilege でそもそも渡さないのが第一原則だが、本ポートでは
「渡ってしまっていても middleware 層で遮断される」ことを実証するため、
意図的にエージェントへ渡す(テストが「実行されないこと」を台帳で証明する)。

``ledger.executed_calls`` は全ツールの**実行**記録(監査ログとは別の、
テスト用の生記録)。ポリシーに遮断された呼び出しはここに現れない。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PaymentRecord:
    payment_id: str
    employee_id: str
    amount_usd: float
    category: str
    description: str


@dataclass
class ExpenseLedger:
    """インメモリ台帳(実運用では会計システム API)。"""

    payments: list[PaymentRecord] = field(default_factory=list)
    deletions: list[str] = field(default_factory=list)
    #: ツールが実際に実行された生記録。「遮断されたら実行されない」ことの証明に使う
    executed_calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)


#: カテゴリ別の社内規程(参照系ツールの決定論データ)
POLICY_NOTES: dict[str, str] = {
    "travel": "Travel: book economy; per-diem $75/day; receipts required above $25.",
    "meals": "Meals: client meals up to $120/person; itemized receipt required.",
    "equipment": "Equipment: purchases above $500 need asset tagging; keep the invoice.",
    "software": "Software: subscriptions must go through IT procurement above $200/year.",
    "training": "Training: pre-approval by manager required above $1,000.",
    "other": "Other: attach justification and a receipt; finance reviews case by case.",
}

#: 部門別の残予算(参照系ツールの決定論データ)
DEPARTMENT_BUDGETS: dict[str, float] = {
    "sales": 12_500.0,
    "engineering": 8_200.0,
    "marketing": 3_900.0,
}


def build_tools(ledger: ExpenseLedger) -> list[Callable[..., str]]:
    """台帳を閉じ込めたツール束を返す(docstring がツール説明になる)。"""

    def lookup_expense_policy(category: str) -> str:
        """Look up the company expense policy for a category (travel, meals, equipment, software, training, other)."""
        ledger.executed_calls.append(("lookup_expense_policy", {"category": category}))
        return POLICY_NOTES.get(category, POLICY_NOTES["other"])

    def check_budget(department: str) -> str:
        """Check the remaining expense budget for a department."""
        ledger.executed_calls.append(("check_budget", {"department": department}))
        remaining = DEPARTMENT_BUDGETS.get(department.lower())
        if remaining is None:
            return f"No budget record for department '{department}'."
        return f"Department '{department}' has ${remaining:,.2f} remaining this quarter."

    def submit_reimbursement(
        employee_id: str, amount_usd: float, category: str, description: str
    ) -> str:
        """Submit an approved reimbursement for payment. Only call this after deciding to approve."""
        ledger.executed_calls.append(
            (
                "submit_reimbursement",
                {
                    "employee_id": employee_id,
                    "amount_usd": amount_usd,
                    "category": category,
                    "description": description,
                },
            )
        )
        payment = PaymentRecord(
            payment_id=f"PAY-{len(ledger.payments) + 1:04d}",
            employee_id=employee_id,
            amount_usd=amount_usd,
            category=category,
            description=description,
        )
        ledger.payments.append(payment)
        return json.dumps(
            {"status": "paid", "payment_id": payment.payment_id, "amount_usd": amount_usd}
        )

    def delete_expense_record(record_id: str) -> str:
        """Delete an expense record from the ledger (destructive)."""
        ledger.executed_calls.append(("delete_expense_record", {"record_id": record_id}))
        ledger.deletions.append(record_id)
        return f"Deleted expense record {record_id}."

    return [lookup_expense_policy, check_budget, submit_reimbursement, delete_expense_record]

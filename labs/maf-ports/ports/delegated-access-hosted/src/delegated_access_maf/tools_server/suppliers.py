"""基幹 API(取引先マスタ)の疑似実装 — 参照は全社員、支払条件の更新は Suppliers.Write のみ。

実物の基幹システムの代わりに ``data/suppliers.json`` をメモリに載せる(プロセスを再起動すると
初期値に戻る)。誰が更新できるかの判定はここではしない — 判定は MCP エンドポイントの前段
(方式 B: ``auth.McpAuthMiddleware`` / 方式 A: APIM)に置き、ここは「検証済みの呼び出し元」を
受け取って入力検証と監査記録だけを行う。
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..jwt_validation import Principal

logger = logging.getLogger("delegated_access_maf.tools_server.audit")

#: 支払サイトの上限(社内規程)
MAX_PAYMENT_TERMS_DAYS = 120
#: 中小受託取引(旧・下請取引)の対象先は受領日から 60 日以内に支払う(社内規程としてモデル化)
MAX_PAYMENT_TERMS_DAYS_SUBCONTRACT = 60


class SupplierNotFoundError(LookupError):
    pass


class InvalidUpdateError(ValueError):
    pass


@dataclass(frozen=True)
class Supplier:
    supplier_id: str
    name: str
    category: str
    payment_terms_days: int
    small_business_subcontract: bool
    status: str = "active"
    updated_at: str | None = None

    def to_summary(self) -> dict[str, Any]:
        return {
            "supplier_id": self.supplier_id,
            "name": self.name,
            "category": self.category,
            "payment_terms_days": self.payment_terms_days,
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AuditRecord:
    """更新 1 回分の監査記録。``oid`` / ``upn`` は検証済みトークンから(ツール引数からではない)。"""

    oid: str
    upn: str | None
    supplier_id: str
    before: int
    after: int
    at: str


class SupplierStore:
    def __init__(self, suppliers: list[Supplier]) -> None:
        self._suppliers = {s.supplier_id: s for s in suppliers}
        self._audit: list[AuditRecord] = []
        self._lock = asyncio.Lock()

    @classmethod
    def from_json(cls, path: Path) -> SupplierStore:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls([Supplier(**item) for item in raw["suppliers"]])

    @property
    def audit_log(self) -> list[AuditRecord]:
        return list(self._audit)

    def all_suppliers(self) -> list[Supplier]:
        return sorted(self._suppliers.values(), key=lambda s: s.supplier_id)

    def get(self, supplier_id: str) -> Supplier:
        key = (supplier_id or "").strip().upper()
        try:
            return self._suppliers[key]
        except KeyError:
            raise SupplierNotFoundError(f"取引先 {supplier_id!r} は存在しません") from None

    @staticmethod
    def validate_days(supplier: Supplier, days: Any) -> int:
        if isinstance(days, bool) or not isinstance(days, int):
            raise InvalidUpdateError("支払サイト(days)は整数の日数で指定してください")
        if not 1 <= days <= MAX_PAYMENT_TERMS_DAYS:
            raise InvalidUpdateError(
                f"支払サイトは 1〜{MAX_PAYMENT_TERMS_DAYS} 日の範囲で指定してください(指定値: {days})"
            )
        if supplier.small_business_subcontract and days > MAX_PAYMENT_TERMS_DAYS_SUBCONTRACT:
            raise InvalidUpdateError(
                f"{supplier.name} は中小受託取引の対象先のため、支払サイトは "
                f"{MAX_PAYMENT_TERMS_DAYS_SUBCONTRACT} 日以内です(指定値: {days})"
            )
        return days

    async def update_payment_terms(
        self, supplier_id: str, days: Any, *, principal: Principal
    ) -> tuple[Supplier, AuditRecord]:
        """支払サイトを更新し、監査記録を 1 件追加する(値が同じでも実行記録として残す)。"""
        async with self._lock:
            current = self.get(supplier_id)
            new_days = self.validate_days(current, days)
            now = datetime.now(UTC).isoformat()
            updated = replace(current, payment_terms_days=new_days, updated_at=now)
            self._suppliers[current.supplier_id] = updated
            record = AuditRecord(
                oid=principal.oid,
                upn=principal.upn,
                supplier_id=current.supplier_id,
                before=current.payment_terms_days,
                after=new_days,
                at=now,
            )
            self._audit.append(record)
        logger.info("supplier_update %s", json.dumps(asdict(record), ensure_ascii=False))
        return updated, record

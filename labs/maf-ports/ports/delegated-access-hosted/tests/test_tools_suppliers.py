"""取引先マスタ(基幹 API の疑似実装)の入力検証と監査記録。"""

from __future__ import annotations

import pytest

from delegated_access_maf.tools_server.settings import DEFAULT_SUPPLIERS_DATA
from delegated_access_maf.tools_server.suppliers import (
    InvalidUpdateError,
    SupplierNotFoundError,
    SupplierStore,
)

from .tools_support import principal


@pytest.fixture
def store() -> SupplierStore:
    return SupplierStore.from_json(DEFAULT_SUPPLIERS_DATA)


def test_bundled_master_has_six_suppliers(store):
    suppliers = store.all_suppliers()
    assert [s.supplier_id for s in suppliers] == [f"S-100{i}" for i in range(1, 7)]
    assert any(s.small_business_subcontract for s in suppliers)
    assert set(suppliers[0].to_summary()) == {
        "supplier_id",
        "name",
        "category",
        "payment_terms_days",
    }


def test_lookup_is_case_insensitive_and_reports_unknown_ids(store):
    assert store.get(" s-1003 ").name == "みなと印刷株式会社"
    with pytest.raises(SupplierNotFoundError):
        store.get("S-9999")


@pytest.mark.parametrize(
    ("supplier_id", "days", "message"),
    [
        ("S-1002", 0, "1〜120"),
        ("S-1002", 121, "1〜120"),
        ("S-1002", "45", "整数"),
        ("S-1002", True, "整数"),
        ("S-1002", 45.0, "整数"),
        ("S-1003", 61, "60 日以内"),  # 中小受託取引の対象先
    ],
)
async def test_invalid_updates_are_rejected_without_audit(store, supplier_id, days, message):
    with pytest.raises(InvalidUpdateError, match=message):
        await store.update_payment_terms(supplier_id, days, principal=principal())
    assert store.audit_log == []


async def test_update_appends_audit_record_from_principal(store):
    who = principal(oid="bbbb", roles=("Suppliers.Write",))
    updated, record = await store.update_payment_terms("s-1005", 60, principal=who)
    assert updated.payment_terms_days == 60 and updated.updated_at
    assert (record.oid, record.upn, record.supplier_id) == (
        "bbbb",
        "bbbb@contoso.example",
        "S-1005",
    )
    assert (record.before, record.after) == (90, 60)
    assert store.get("S-1005").payment_terms_days == 60

    # 同じ値でも実行した事実は残す
    _, again = await store.update_payment_terms("S-1005", 60, principal=who)
    assert (again.before, again.after) == (60, 60)
    assert len(store.audit_log) == 2


async def test_unknown_supplier_update_is_not_audited(store):
    with pytest.raises(SupplierNotFoundError):
        await store.update_payment_terms("S-0000", 30, principal=principal())
    assert store.audit_log == []

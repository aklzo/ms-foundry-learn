"""ハッシュ連鎖監査ログ: 正常系・改ざん検知・独立検証(JSON)・決定論。"""

from __future__ import annotations

import json
from itertools import count

from governed_agent_maf.audit import (
    GENESIS_HASH,
    AuditTrail,
    load_entries,
    sha256_text,
    verify_entries,
)


def make_trail(n: int = 3) -> AuditTrail:
    ticks = count()
    trail = AuditTrail(time_fn=lambda: 1000.0 + next(ticks))
    for i in range(n):
        trail.record(
            actor="expense_approver",
            action=f"tool:submit_reimbursement_{i}",
            input_text=f'{{"amount_usd": {100 + i}}}',
            output_text=f'{{"payment_id": "PAY-{i:04d}"}}',
            detail="allow:POLICY-DEFAULT",
        )
    return trail


def test_empty_chain_is_valid() -> None:
    assert AuditTrail().verify_chain() == (True, None)


def test_chain_links_and_verifies() -> None:
    trail = make_trail(3)
    entries = trail.entries
    assert entries[0].previous_hash == GENESIS_HASH
    assert entries[1].previous_hash == entries[0].entry_hash
    assert entries[2].previous_hash == entries[1].entry_hash
    assert [e.sequence for e in entries] == [0, 1, 2]
    assert trail.verify_chain() == (True, None)


def test_input_output_are_stored_as_hashes_only() -> None:
    trail = AuditTrail(time_fn=lambda: 1000.0)
    entry = trail.record(
        actor="a", action="agent_run", input_text="secret request", output_text="secret reply"
    )
    assert entry.input_hash == sha256_text("secret request")
    assert entry.output_hash == sha256_text("secret reply")
    assert "secret" not in trail.to_json()


def test_deterministic_with_fixed_time() -> None:
    assert make_trail(3).to_json() == make_trail(3).to_json()


def test_tampered_field_is_detected() -> None:
    entries = [e for e in json.loads(make_trail(3).to_json())]
    entries[1]["detail"] = "allow:FORGED"
    valid, error = verify_entries(entries)
    assert not valid
    assert "entry 1" in error
    assert "entry_hash" in error


def test_tampered_output_hash_is_detected() -> None:
    entries = json.loads(make_trail(3).to_json())
    entries[0]["output_hash"] = sha256_text("forged output")
    valid, error = verify_entries(entries)
    assert not valid
    assert "entry 0" in error


def test_removed_entry_breaks_chain() -> None:
    entries = json.loads(make_trail(3).to_json())
    del entries[1]
    valid, error = verify_entries(entries)
    assert not valid
    assert "entry 1" in error


def test_reordered_entries_break_chain() -> None:
    entries = json.loads(make_trail(3).to_json())
    entries[1], entries[2] = entries[2], entries[1]
    valid, _ = verify_entries(entries)
    assert not valid


def test_export_is_independently_verifiable() -> None:
    """エクスポート JSON は AuditTrail 無しで(dict 列のまま)検証できる。"""
    exported = make_trail(4).to_json()
    entries = load_entries(exported)
    assert verify_entries(entries) == (True, None)

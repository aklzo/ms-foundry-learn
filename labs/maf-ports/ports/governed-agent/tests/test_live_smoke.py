"""ライブスモーク(手動・要 labs/maf-ports/.env)。

    uv sync --extra dev --extra live && uv run pytest -m live

実モデルで経費精算パイプラインを 2 ケース流す:
1. 正常系: 上限内・領収書ありの申請 → 支払いまで到達、監査連鎖が有効
2. ガバナンス系: ハード上限超過の申請 → **支払いが発生しないこと**
   (ポリシー middleware の決定論保証。モデルの挙動に依存しない)

営業時間ルールは clock 固定(水曜 10:30)でスモーク実行時刻に依存させない。
トレースは App Insights(setup_tracing)で: invoke_agent / execute_tool
スパンがポータルに出ることを目視確認する。
"""

from __future__ import annotations

import pytest

from governed_agent_maf.config import ConfigError, FoundrySettings

pytestmark = pytest.mark.live

CASE_TIMEOUT_SECONDS = 180.0


@pytest.fixture()
def settings() -> FoundrySettings:
    try:
        return FoundrySettings.from_env()
    except ConfigError as exc:
        pytest.skip(f"live 設定なし: {exc}")


def _build(settings: FoundrySettings):
    from conftest import BUSINESS_NOW, fixed_clock

    from governed_agent_maf.agents import build_agents, build_chat_client, build_governance
    from governed_agent_maf.observability import setup_tracing
    from governed_agent_maf.pipeline import ExpenseCasePipeline

    setup_tracing(settings.app_insights_connection_string)
    gov = build_governance(clock=fixed_clock(BUSINESS_NOW))
    agents = build_agents(build_chat_client(settings), gov)
    return ExpenseCasePipeline(agents, gov), gov


async def test_live_happy_path_pays_within_limit(settings: FoundrySettings) -> None:
    import asyncio

    pipeline, gov = _build(settings)
    result = await asyncio.wait_for(
        pipeline.process(
            "Please reimburse my client dinner with Fabrikam on 2026-07-24: $180, "
            "itemized receipt RCPT-2201 attached. Employee E-1042 (Mika Tanaka), "
            "sales department, category meals."
        ),
        timeout=CASE_TIMEOUT_SECONDS,
    )

    # 抽出(LLM)が実データを拾えている
    assert result.claim.employee_id == "E-1042"
    assert result.claim.amount_usd == pytest.approx(180.0, abs=1.0)
    assert result.claim.has_receipt
    # ゲート 2 段を通過し、支払いまで到達
    assert result.intake_gate.passed
    assert result.inspection_gate is not None and result.inspection_gate.passed
    assert result.status == "paid", result.approver_reply
    assert len(result.payments) == 1
    assert result.payments[0].amount_usd <= gov.policy.auto_approve_limit_usd
    # 監査連鎖が有効で、ツール実行が記録されている
    assert result.chain_valid, result.chain_error
    assert any(e.action == "tool:submit_reimbursement" for e in gov.audit.entries)


async def test_live_hard_limit_never_pays(settings: FoundrySettings) -> None:
    """モデルが何を試みても、ハード上限超過の支払いは決定論的に発生しない。"""
    import asyncio

    pipeline, gov = _build(settings)
    result = await asyncio.wait_for(
        pipeline.process(
            "Please reimburse my new workstation purchased on 2026-07-20 for the ML team: "
            "$12,000, vendor invoice INV-5518 attached. Employee E-2077 (Ken Sato), "
            "engineering department, category equipment."
        ),
        timeout=CASE_TIMEOUT_SECONDS,
    )

    # ポリシー保証: 支払いは存在しえない(ここがこのスモークの本体)
    assert gov.ledger.payments == []
    assert result.status != "paid"
    assert result.chain_valid, result.chain_error
    # モデルが submit を試みていれば、遮断の監査エントリが残っている
    denied = [e for e in gov.audit.entries if e.detail.startswith("deny:AMT-001")]
    if result.status == "blocked_by_policy":
        assert denied, "blocked なのに遮断エントリが無い"

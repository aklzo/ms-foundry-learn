"""CLI エントリポイント。

    uv run governed-agent-maf --request "Team dinner $180 ..., receipt attached"
    uv run governed-agent-maf --script tests/data/expense_requests.txt
    uv run governed-agent-maf                      # 対話(1 行 = 1 申請)
    uv run governed-agent-maf --verify runs/audit.json   # 監査連鎖の独立検証(モデル不要)

対話コマンド: /audit(監査連鎖の要約)/queue(承認待ち)/quit(終了)。
--now で「現在時刻」を固定できる(営業時間ルールのデモ・再現用)。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from .agents import build_agents, build_chat_client, build_governance
from .audit import load_entries, verify_entries
from .config import ConfigError, FoundrySettings
from .observability import setup_tracing
from .pipeline import CaseResult, ExpenseCasePipeline
from .policies import GovernancePolicy
from .trust import DEFAULT_TRUST_THRESHOLD

#: 1 ケースあたりの安全弁
DEFAULT_CASE_TIMEOUT_SECONDS = 180.0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ガバナンス層つき経費精算エージェント(MAF middleware 版)"
    )
    parser.add_argument("--request", default=None, help="経費申請テキスト(1 ケース実行)")
    parser.add_argument(
        "--script", type=Path, default=None, help="申請スクリプト(1 行 = 1 ケース)を再生"
    )
    parser.add_argument("--json", action="store_true", help="ケース結果を JSON で出す")
    parser.add_argument("--output", type=Path, default=None, help="ケース結果 JSON の書き出し先")
    parser.add_argument(
        "--audit-export", type=Path, default=None, help="監査連鎖 JSON の書き出し先"
    )
    parser.add_argument(
        "--verify",
        type=Path,
        default=None,
        help="エクスポート済み監査連鎖 JSON を検証して終了(Foundry 不要)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=DEFAULT_TRUST_THRESHOLD,
        help=f"信頼ゲート閾値(既定 {DEFAULT_TRUST_THRESHOLD})",
    )
    parser.add_argument(
        "--auto-approve-limit", type=float, default=None, help="自動承認上限 USD(既定 1000)"
    )
    parser.add_argument(
        "--hard-limit", type=float, default=None, help="ハード上限 USD(既定 5000)"
    )
    parser.add_argument(
        "--now",
        default=None,
        help="営業時間判定に使う現在時刻(ISO 形式)。省略時はシステム時刻",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_CASE_TIMEOUT_SECONDS,
        help=f"1 ケースのタイムアウト秒(既定 {DEFAULT_CASE_TIMEOUT_SECONDS:.0f})",
    )
    args = parser.parse_args()

    if args.verify is not None:
        sys.exit(_verify_export(args.verify))

    try:
        asyncio.run(_run(args))
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(130)


def _verify_export(path: Path) -> int:
    """監査連鎖 JSON の独立検証(SHA-256 だけで完結。改ざんがあれば 1)。"""
    entries = load_entries(path.read_text(encoding="utf-8"))
    valid, error = verify_entries(entries)
    if valid:
        print(f"chain OK: {len(entries)} entries, no tampering detected")
        return 0
    print(f"chain BROKEN: {error}", file=sys.stderr)
    return 1


def _build_policy(args: argparse.Namespace) -> GovernancePolicy:
    overrides: dict[str, float] = {}
    if args.auto_approve_limit is not None:
        overrides["auto_approve_limit_usd"] = args.auto_approve_limit
    if args.hard_limit is not None:
        overrides["hard_limit_usd"] = args.hard_limit
    return GovernancePolicy(**overrides)


def _print_case(result: CaseResult, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result.to_dict(), indent=2, default=str))
        return
    print(f"\n=== {result.case_id}: {result.status} ===")
    claim = result.claim
    amount = f"${claim.amount_usd:,.2f}" if claim.amount_usd is not None else "?"
    print(f"  claim: {claim.employee_id} / {claim.category} / {amount}")
    gate = result.intake_gate
    print(f"  intake trust: {gate.trust.score} ({gate.trust.tier}) -> {gate.tag}")
    if result.inspection_gate is not None:
        gate = result.inspection_gate
        rec = result.report.recommendation if result.report else "?"
        print(f"  inspection: {rec} / trust {gate.trust.score} ({gate.trust.tier}) -> {gate.tag}")
    for payment in result.payments:
        print(f"  payment: {payment.payment_id} ${payment.amount_usd:,.2f}")
    for ticket in result.tickets:
        print(f"  HITL: {ticket.ticket_id} [{ticket.kind}] {ticket.reason}")
    if result.approver_reply:
        print(f"  approver: {result.approver_reply}")
    chain = "OK" if result.chain_valid else f"BROKEN: {result.chain_error}"
    print(f"  audit: {result.audit_entries} entries, chain {chain}")


async def _run(args: argparse.Namespace) -> None:
    settings = FoundrySettings.from_env()
    if setup_tracing(settings.app_insights_connection_string):
        print("[trace] Application Insights 送信を有効化")

    clock = datetime.now if args.now is None else _fixed_clock(args.now)
    gov = build_governance(_build_policy(args), threshold=args.threshold, clock=clock)
    agents = build_agents(build_chat_client(settings), gov)
    pipeline = ExpenseCasePipeline(agents, gov)

    results: list[CaseResult] = []

    async def run_case(text: str) -> None:
        result = await asyncio.wait_for(pipeline.process(text), timeout=args.timeout)
        results.append(result)
        _print_case(result, args.json)

    if args.request is not None:
        await run_case(args.request)
    elif args.script is not None:
        for line in _load_script(args.script):
            print(f"\n>>> {line}")
            await run_case(line)
    else:
        await _interactive(run_case, gov)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps([r.to_dict() for r in results], indent=2, default=str), encoding="utf-8"
        )
        print(f"[out] {args.output}")
    if args.audit_export is not None:
        args.audit_export.parent.mkdir(parents=True, exist_ok=True)
        args.audit_export.write_text(gov.audit.to_json(), encoding="utf-8")
        print(f"[audit] {args.audit_export}(--verify で独立検証可)")


async def _interactive(run_case, gov) -> None:
    print("経費申請を 1 行で入力(/audit /queue /quit)")
    loop = asyncio.get_event_loop()
    while True:
        try:
            line = (await loop.run_in_executor(None, input, "> ")).strip()
        except EOFError:
            break
        if not line:
            continue
        if line in {"/quit", "/q"}:
            break
        if line == "/audit":
            valid, error = gov.audit.verify_chain()
            state = "OK" if valid else f"BROKEN: {error}"
            print(f"audit chain: {len(gov.audit.entries)} entries, {state}")
            for entry in gov.audit.entries:
                print(
                    f"  #{entry.sequence} {entry.actor} {entry.action} "
                    f"[{entry.detail}] {entry.entry_hash[:16]}..."
                )
            continue
        if line == "/queue":
            pending = gov.queue.pending()
            print(f"pending approvals: {len(pending)}")
            for ticket in pending:
                print(f"  {ticket.ticket_id} [{ticket.kind}] {ticket.reason}")
            continue
        await run_case(line)


def _fixed_clock(text: str):
    fixed = datetime.fromisoformat(text)

    def clock() -> datetime:
        return fixed

    return clock


def _load_script(path: Path) -> list[str]:
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return lines

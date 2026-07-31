"""CLI エントリポイント(テキスト対話層)。

    uv run claim-voice-live-maf                       # 対話(stdin ループ)
    uv run claim-voice-live-maf --script fnol.txt     # スクリプト自動再生
    uv run claim-voice-live-maf --script fnol.txt --json --output runs/state.json

対話は請求者役でテキストを打つ。毎ターン FNOL コアが走り、次に聞くべき質問と
ルーティング判定が返る。/packet で現在のパケット Markdown、/quit(または EOF)
で終了しパケットを表示する。音声セッションは scripts/voice_session.py(要
--extra voice)。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .agents import build_agents, build_chat_client
from .config import ConfigError, FoundrySettings
from .conversation import ClaimIntakeConversation, load_script, run_script
from .observability import setup_tracing
from .schemas import IntakeState

#: 1 ターンあたりの安全弁(元アプリに全体タイムアウトは無い。運用上の追加)
DEFAULT_TURN_TIMEOUT_SECONDS = 120.0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="保険事故受付(FNOL)エージェント(MAF + Foundry / Voice Live 移植版)"
    )
    parser.add_argument(
        "--script", type=Path, default=None, help="請求者発話スクリプト(1 行 1 発話)を自動再生"
    )
    parser.add_argument("--json", action="store_true", help="最終 IntakeState を JSON で出す")
    parser.add_argument("--output", type=Path, default=None, help="最終 IntakeState JSON の書き出し先")
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TURN_TIMEOUT_SECONDS,
        help=f"1 ターンのタイムアウト秒(既定 {DEFAULT_TURN_TIMEOUT_SECONDS:.0f})",
    )
    args = parser.parse_args()
    try:
        asyncio.run(_run(args))
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(130)


def _print_turn_summary(state: IntakeState) -> None:
    validation = state.validation
    print(
        f"  [route={state.route} type={state.classification.claim_type} "
        f"missing={len(validation.missing_fields)}]",
        file=sys.stderr,
    )
    print(f"Agent> {state.next_question}")


async def _run(args: argparse.Namespace) -> None:
    settings = FoundrySettings.from_env()
    if setup_tracing(settings.app_insights_connection_string):
        print("tracing: App Insights 有効", file=sys.stderr)

    conversation = ClaimIntakeConversation(agents=build_agents(build_chat_client(settings)))
    print(f"Agent> {conversation.transcript[0].text}")

    if args.script is not None:
        lines = load_script(args.script)

        async def scripted() -> None:
            def on_state(line: str, state: IntakeState) -> None:
                print(f"Claimant> {line}")
                _print_turn_summary(state)

            await run_script(conversation, lines, on_state=on_state)

        await asyncio.wait_for(scripted(), args.timeout * max(1, len(lines)))
    else:
        await _interactive(conversation, args.timeout)

    _emit_final(conversation.state, args)


async def _interactive(conversation: ClaimIntakeConversation, timeout: float) -> None:
    print("(claimant として入力。/packet で現在のパケット、/quit で終了)", file=sys.stderr)
    while True:
        try:
            line = input("Claimant> ").strip()
        except EOFError:
            break
        if not line:
            continue
        if line == "/quit":
            break
        if line == "/packet":
            print(conversation.state.packet.markdown)
            continue
        try:
            state = await asyncio.wait_for(conversation.claimant_turn(line), timeout)
        except TimeoutError:
            print(f"error: turn timed out after {timeout:.0f}s", file=sys.stderr)
            continue
        _print_turn_summary(state)


def _emit_final(state: IntakeState, args: argparse.Namespace) -> None:
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[saved] {args.output}", file=sys.stderr)
    if args.json:
        print(json.dumps(state.to_dict(), ensure_ascii=False, indent=2))
    else:
        print()
        print(state.packet.markdown)


if __name__ == "__main__":
    main()

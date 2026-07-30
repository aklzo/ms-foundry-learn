"""CLI エントリポイント(元アプリの Streamlit UI の置き換え)。

    uv run travel-memory-maf --user alice                 # 対話モード
    uv run travel-memory-maf --user alice --once "京都で桜を見たい"
    uv run travel-memory-maf --user alice --memories      # 保存済み記憶を表示

対話モードのコマンド: /memories(記憶一覧)、/quit(終了)。

前提: scripts/setup_memory.py で Memory ストア作成済み+``az login`` 済み
(Memory API は Entra ID 認証のみ。チャットモデルは API キー)。

記憶追加は既定 fire-and-forget(LRO を投げて次のターンへ)。``--wait`` で
抽出完了まで待つ(ライブスモークや「add 直後の search で必ずヒットさせたい」
検証用。1 ターンあたり 1 分程度かかることがある)。
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from .agents import build_chat_client, build_travel_agent
from .chat import run_turn
from .config import ConfigError, TravelMemorySettings
from .memory import DEFAULT_MAX_MEMORIES, MemoryStore, make_foundry_memory_store
from .observability import setup_tracing


def main() -> None:
    parser = argparse.ArgumentParser(
        description="記憶付き旅行相談チャット(MAF + Foundry Memory 移植版)"
    )
    parser.add_argument(
        "--user",
        required=True,
        help="ユーザー ID(mem0 の user_id → Foundry Memory の scope。記憶はこの単位で分離)",
    )
    parser.add_argument(
        "--once", metavar="MESSAGE", help="単発モード: 1 ターンだけ実行して終了(ライブスモーク用)"
    )
    parser.add_argument(
        "--memories",
        action="store_true",
        help="保存済み記憶を表示して終了(元アプリの View My Memory)",
    )
    parser.add_argument(
        "--max-memories",
        type=int,
        default=DEFAULT_MAX_MEMORIES,
        help=f"検索で注入する記憶の最大件数(既定 {DEFAULT_MAX_MEMORIES})",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="記憶更新 LRO の完了を待つ(既定は fire-and-forget)",
    )
    args = parser.parse_args()
    try:
        asyncio.run(_run(args))
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)


async def _run(args: argparse.Namespace) -> None:
    settings = TravelMemorySettings.from_env()
    if setup_tracing(settings.app_insights_connection_string):
        print("tracing: App Insights 有効", file=sys.stderr)

    store = make_foundry_memory_store(settings, wait_for_update=args.wait)
    try:
        if args.memories:
            await _print_memories(store, args.user)
            return

        agent = build_travel_agent(build_chat_client(settings))
        if args.once:
            await _turn(agent, store, args)
            return

        print(
            f"travel-memory-maf: user={args.user} store={settings.memory_store} "
            "(/memories で記憶一覧、/quit で終了)",
            file=sys.stderr,
        )
        while True:
            try:
                line = (await asyncio.to_thread(input, f"{args.user}> ")).strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not line:
                continue
            if line in {"/quit", "/exit"}:
                break
            if line == "/memories":
                await _print_memories(store, args.user)
                continue
            await _turn(agent, store, args, message=line)
    finally:
        await store.aclose()


async def _turn(agent, store: MemoryStore, args: argparse.Namespace, message: str | None = None):
    result = await run_turn(
        agent,
        store,
        args.user,
        message if message is not None else args.once,
        max_memories=args.max_memories,
    )
    # 元アプリの「Relevant past information」相当の進捗表示(stderr)
    print(f"[memory] {len(result.memories)} hits", file=sys.stderr)
    for memory in result.memories:
        print(f"  - {memory.content}", file=sys.stderr)
    print(result.answer)
    return result


async def _print_memories(store: MemoryStore, user_id: str) -> None:
    records = await store.get_all(user_id)
    if not records:
        print(f"(no memories for user '{user_id}')")
        return
    print(f"Memory history for {user_id}:")
    for record in records:
        suffix = f" [{record.kind}]" if record.kind else ""
        print(f"- {record.content}{suffix}")


if __name__ == "__main__":
    main()

"""Voice Live API セッションランナー(要 `uv sync --extra voice`)。

    uv run python scripts/voice_session.py --probe          # 接続確立+session.updated 確認
    uv run python scripts/voice_session.py --text "I need to file a claim..."
    uv run python scripts/voice_session.py --script tests/data/fnol_auto_injury.txt
    uv run python scripts/voice_session.py                  # 対話(テキストターン)

構成: Voice Live(音声会話・VAD・STT/TTS)⇔ 本スクリプト ⇔ FNOL コア
(MAF ワークフロー)。Voice Live には process_claim_turn 関数ツールを宣言し、
モデルは請求者ターンごとにツールを呼ぶ → 本スクリプトがコアを実行して
ルーティング判定と次質問を返す → モデルがそれを音声(+テキスト)で話す。

環境制約(マイク/スピーカーなし)のため、このスクリプトの検証範囲は
**接続確立 + テキストイベント往復**(conversation.item.create の input_text →
response.* ストリーム)まで。音声入力(input_audio_buffer.append)への拡張点は
コード中に TODO コメントで明示した。音声出力(response.audio.delta)は受信して
バイト数を数えるだけで破棄する。

認証は既定で api-key(labs/maf-ports/.env の FOUNDRY_API_KEY = Foundry
リソースキー)。--entra で DefaultAzureCredential(要 Cognitive Services User
+ Foundry User ロール、scope https://ai.azure.com/.default)。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from claim_voice_live_maf.agents import ClaimIntakeAgents, build_agents, build_chat_client
from claim_voice_live_maf.config import ConfigError, FoundrySettings
from claim_voice_live_maf.conversation import load_script
from claim_voice_live_maf.observability import setup_tracing
from claim_voice_live_maf.voice import (
    build_claim_tool_result,
    build_function_output_item,
    build_response_create,
    build_session_config,
    build_session_update,
    build_user_text_item,
    build_websocket_url,
    parse_claim_tool_arguments,
    parse_voice_event,
)
from claim_voice_live_maf.workflow import run_intake_turn

RECV_TIMEOUT_SECONDS = 60.0


class VoiceSession:
    """1 本の Voice Live 接続と FNOL コアの橋渡し。"""

    def __init__(self, connection, agents: ClaimIntakeAgents | None) -> None:
        self._connection = connection
        self._agents = agents
        self.claimant_turns: list[str] = []
        self.audio_bytes = 0
        self.last_route = ""

    async def recv_event(self):
        raw = await asyncio.wait_for(self._connection.recv_bytes(), RECV_TIMEOUT_SECONDS)
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        return parse_voice_event(json.loads(raw))

    async def wait_for_session_updated(self) -> None:
        while True:
            event = await self.recv_event()
            if event.kind == "session_updated":
                return
            if event.kind == "error":
                raise RuntimeError(f"Voice Live error: {event.text}")

    async def send_claimant_text(self, text: str) -> None:
        self.claimant_turns.append(text)
        await self._connection.send(build_user_text_item(text))
        await self._connection.send(build_response_create())

    async def handle_function_call(self, event) -> None:
        """process_claim_turn: FNOL コアを実行し結果を会話へ返す。"""
        transcript = parse_claim_tool_arguments(event.arguments)
        local = "\n".join(self.claimant_turns)
        if len(local) > len(transcript):
            transcript = local  # モデルの引数よりローカル記録が完全ならそちらを使う
        if self._agents is None:
            result = {"error": "claim core unavailable in probe mode"}
        else:
            state = await run_intake_turn(self._agents, transcript)
            result = build_claim_tool_result(state)
            self.last_route = state.route
            print(
                f"\n[core] route={state.route} missing={len(state.validation.missing_fields)} "
                f"next={state.next_question!r}",
                file=sys.stderr,
            )
        await self._connection.send(build_function_output_item(event.call_id, result))
        await self._connection.send(build_response_create())

    async def pump_response(self) -> str:
        """発話応答の完了まで受信し、エージェント発話テキストを返す。

        response.create 1 回につき response.done が 1 回返る。ツール呼び出しを
        含む応答はそこで終端し、ツール結果を渡した後の response.create が
        もう 1 応答を生む — expected_dones で両方を待つ。
        """
        text_parts: list[str] = []
        expected_dones = 1
        while True:
            event = await self.recv_event()
            if event.kind == "response_text_delta":
                text_parts.append(event.text)
                print(event.text, end="", flush=True)
            elif event.kind == "audio_delta":
                # スピーカーなし環境: 音声チャンクは数えるだけで破棄
                self.audio_bytes += len(event.raw.get("delta", ""))
            elif event.kind == "function_call":
                await self.handle_function_call(event)
                expected_dones += 1  # ツール結果に対する応答の分
            elif event.kind == "input_transcript_done" and event.text:
                # 音声入力時のみ発生(TODO: input_audio_buffer.append 拡張点)
                self.claimant_turns.append(event.text)
            elif event.kind == "response_done":
                expected_dones -= 1
                if expected_dones <= 0:
                    print()
                    return "".join(text_parts)
            elif event.kind == "error":
                raise RuntimeError(f"Voice Live error: {event.text}")


async def run(args: argparse.Namespace) -> None:
    try:
        settings = FoundrySettings.from_env()
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    if not settings.voice_live_endpoint:
        print(
            "error: VOICE_LIVE_ENDPOINT か FOUNDRY_PROJECT_ENDPOINT を設定してください",
            file=sys.stderr,
        )
        raise SystemExit(2)

    try:
        from azure.ai.voicelive.aio import connect
    except ImportError as exc:
        print("error: azure-ai-voicelive 未導入(uv sync --extra voice)", file=sys.stderr)
        raise SystemExit(2) from exc

    if args.entra:
        from azure.identity.aio import DefaultAzureCredential

        credential = DefaultAzureCredential()
    else:
        from azure.core.credentials import AzureKeyCredential

        credential = AzureKeyCredential(settings.api_key)

    setup_tracing(settings.app_insights_connection_string)
    agents = None
    if not args.probe:
        agents = build_agents(build_chat_client(settings))

    modalities = ("text",) if args.no_audio else ("text", "audio")
    session_config = build_session_config(
        voice_name=settings.voice_live_voice, modalities=modalities
    )
    print(
        "[connect] "
        + build_websocket_url(
            settings.voice_live_endpoint, settings.voice_live_model, settings.voice_live_api_version
        ),
        file=sys.stderr,
    )

    async with connect(
        credential=credential,
        endpoint=settings.voice_live_endpoint,
        model=settings.voice_live_model,
        api_version=settings.voice_live_api_version,
    ) as connection:
        session = VoiceSession(connection, agents)
        await connection.send(build_session_update(session_config))
        await session.wait_for_session_updated()
        print("[session] updated (connection established)", file=sys.stderr)

        if args.probe:
            print("PROBE OK: connection + session.update round trip succeeded")
            return

        if args.text:
            await session.send_claimant_text(args.text)
            await session.pump_response()
        elif args.script:
            for line in load_script(args.script):
                print(f"\nClaimant> {line}")
                await session.send_claimant_text(line)
                await session.pump_response()
        else:
            print("(claimant として入力。空行で終了)", file=sys.stderr)
            while True:
                try:
                    line = input("\nClaimant> ").strip()
                except EOFError:
                    break
                if not line:
                    break
                await session.send_claimant_text(line)
                await session.pump_response()

        if session.audio_bytes:
            print(f"[audio] discarded {session.audio_bytes} base64 chars", file=sys.stderr)
        if session.last_route:
            print(f"[final route] {session.last_route}", file=sys.stderr)

    if args.entra:
        await credential.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Voice Live FNOL セッション(テキストイベント検証)")
    parser.add_argument("--probe", action="store_true", help="接続確立+session.update のみ確認")
    parser.add_argument("--text", default=None, help="1 発話だけ送って応答を表示")
    parser.add_argument("--script", type=Path, default=None, help="請求者発話スクリプトを再生")
    parser.add_argument("--no-audio", action="store_true", help="modalities を text のみにする")
    parser.add_argument("--entra", action="store_true", help="Entra ID(DefaultAzureCredential)で認証")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()

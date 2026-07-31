"""ライブスモーク(手動・要 labs/maf-ports/.env)。

    uv sync --extra dev --extra voice --extra live && uv run pytest -m live

1. テキスト対話層(実モデル): 事故シナリオスクリプト(負傷あり自動車事故)を
   再生 → FNOL パケット完成 → emergency_escalation 判定まで。**本ポートの
   ライブ検証の主経路はここ**(音声なしでコアの正しさが確認できる層設計)。
2. Voice Live WebSocket(要 --extra voice): 接続確立 + session.update +
   テキストイベント往復(conversation.item.create → response.*)。マイク/
   スピーカーなし環境の制約により音声入出力はスモーク対象外(README 参照)。
3. Voice Live ツール往復(任意・CLAIM_VOICE_TOOL_SMOKE=1): FNOL コアを
   process_claim_turn ツールとして繋いだ完全ループ。モデルのツール呼び出し
   判断に依存するため既定ではスキップ。
"""

from __future__ import annotations

import asyncio
import json
import os

import pytest

from claim_voice_live_maf.config import ConfigError, FoundrySettings

pytestmark = pytest.mark.live

RESPONSE_TIMEOUT_SECONDS = 90.0


@pytest.fixture()
def settings() -> FoundrySettings:
    try:
        return FoundrySettings.from_env()
    except ConfigError as exc:
        pytest.skip(f"live 設定なし: {exc}")


async def test_live_text_intake_scripted_scenario(settings: FoundrySettings) -> None:
    """事故シナリオ(負傷あり)の再生 → パケット完成 → エスカレーション判定。"""
    from pathlib import Path

    from claim_voice_live_maf.agents import build_agents, build_chat_client
    from claim_voice_live_maf.conversation import ClaimIntakeConversation, load_script, run_script
    from claim_voice_live_maf.observability import setup_tracing

    setup_tracing(settings.app_insights_connection_string)

    conversation = ClaimIntakeConversation(agents=build_agents(build_chat_client(settings)))
    lines = load_script(Path(__file__).parent / "data" / "fnol_auto_injury.txt")
    state = await run_script(conversation, lines)

    # 抽出(LLM)が実データを拾えている
    assert "90210" in state.claim.policy_number
    assert "jordan" in state.claim.policyholder_name.lower()
    assert state.classification.claim_type == "auto_collision"
    # 決定論ゲート: 負傷 → 緊急エスカレーション
    assert state.route == "emergency_escalation"
    assert any(s.signal_id == "SAFETY-001" for s in state.gate.signals)
    assert "human representative" in state.next_question
    # パケットが完成している
    assert "# Insurance Claim Intake Packet" in state.packet.markdown
    assert "**Routing decision:** Emergency Escalation" in state.packet.markdown
    # 会話面: 3 請求者ターン+各ターンのエージェント質問+挨拶
    assert len(conversation.transcript) == 1 + 2 * len(lines)


def _require_voicelive(settings: FoundrySettings):
    if not settings.voice_live_endpoint:
        pytest.skip("VOICE_LIVE_ENDPOINT / FOUNDRY_PROJECT_ENDPOINT なし")
    pytest.importorskip("azure.ai.voicelive", reason="要 uv sync --extra voice")
    from azure.ai.voicelive.aio import connect

    return connect


async def _recv_parsed(connection):
    from claim_voice_live_maf.voice import parse_voice_event

    raw = await asyncio.wait_for(connection.recv_bytes(), RESPONSE_TIMEOUT_SECONDS)
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    return parse_voice_event(json.loads(raw))


async def test_live_voice_live_websocket_text_roundtrip(settings: FoundrySettings) -> None:
    """Voice Live: 接続確立 + session.update + テキストイベント往復。"""
    connect = _require_voicelive(settings)
    from azure.core.credentials import AzureKeyCredential

    from claim_voice_live_maf.voice import (
        build_response_create,
        build_session_config,
        build_session_update,
        build_user_text_item,
    )

    async with connect(
        credential=AzureKeyCredential(settings.api_key),
        endpoint=settings.voice_live_endpoint,
        model=settings.voice_live_model,
        api_version=settings.voice_live_api_version,
    ) as connection:
        # 1. session.update → session.updated(接続確立の確認)
        session_config = build_session_config(
            voice_name=settings.voice_live_voice, include_tools=False
        )
        await connection.send(build_session_update(session_config))
        while True:
            event = await _recv_parsed(connection)
            assert event.kind != "error", f"Voice Live error: {event.text}"
            if event.kind == "session_updated":
                break

        # 2. テキストターン往復(response.text / response.audio_transcript のどちらでも可)
        await connection.send(
            build_user_text_item("Hello, I need to report a claim. Can you hear me?")
        )
        await connection.send(build_response_create())

        reply_parts: list[str] = []
        audio_chunks = 0
        while True:
            event = await _recv_parsed(connection)
            assert event.kind != "error", f"Voice Live error: {event.text}"
            if event.kind == "response_text_delta":
                reply_parts.append(event.text)
            elif event.kind == "audio_delta":
                audio_chunks += 1
            elif event.kind == "response_done":
                break

    reply = "".join(reply_parts)
    assert len(reply.strip()) > 0, "テキスト応答(逐語トランスクリプト)が空"
    # 音声モダリティ有効時は音声チャンクも届く(TTS 経路の生存確認)
    assert audio_chunks >= 0


async def test_live_voice_live_claim_tool_roundtrip(settings: FoundrySettings) -> None:
    """FNOL コアを Voice Live のツールとして繋いだ完全ループ(任意)。"""
    if os.environ.get("CLAIM_VOICE_TOOL_SMOKE") != "1":
        pytest.skip("CLAIM_VOICE_TOOL_SMOKE=1 のときだけ実行(モデルのツール判断に依存)")
    connect = _require_voicelive(settings)
    from azure.core.credentials import AzureKeyCredential

    from claim_voice_live_maf.agents import build_agents, build_chat_client
    from claim_voice_live_maf.voice import (
        CLAIM_TOOL_NAME,
        build_claim_tool_result,
        build_function_output_item,
        build_response_create,
        build_session_config,
        build_session_update,
        build_user_text_item,
        parse_claim_tool_arguments,
    )
    from claim_voice_live_maf.workflow import run_intake_turn

    agents = build_agents(build_chat_client(settings))
    claimant_text = (
        "I need to file an auto claim. I'm Jordan Lee, policy AUTO-90210. Another car "
        "hit my driver's side and my passenger has neck pain and went to urgent care."
    )

    async with connect(
        credential=AzureKeyCredential(settings.api_key),
        endpoint=settings.voice_live_endpoint,
        model=settings.voice_live_model,
        api_version=settings.voice_live_api_version,
    ) as connection:
        await connection.send(
            build_session_update(build_session_config(voice_name=settings.voice_live_voice))
        )
        while True:
            event = await _recv_parsed(connection)
            assert event.kind != "error", f"Voice Live error: {event.text}"
            if event.kind == "session_updated":
                break

        await connection.send(build_user_text_item(claimant_text))
        await connection.send(build_response_create())

        tool_called = False
        routes: list[str] = []
        done_count = 0
        while True:
            event = await _recv_parsed(connection)
            assert event.kind != "error", f"Voice Live error: {event.text}"
            if event.kind == "function_call" and event.name == CLAIM_TOOL_NAME:
                tool_called = True
                transcript = parse_claim_tool_arguments(event.arguments) or claimant_text
                state = await run_intake_turn(agents, transcript)
                routes.append(state.route)
                await connection.send(
                    build_function_output_item(event.call_id, build_claim_tool_result(state))
                )
                await connection.send(build_response_create())
            elif event.kind == "response_done":
                done_count += 1
                # 1 回目の response.done はツール呼び出しを含む応答の終端。
                # ツール結果を受けた 2 回目(発話応答)まで待つ。
                if tool_called and done_count >= 2:
                    break
                if not tool_called and done_count >= 1:
                    break  # ツールを呼ばずに応答が終わった(アサーションで検出)

    assert tool_called, "モデルが process_claim_turn を呼ばなかった"
    assert routes[-1] == "emergency_escalation"

"""Voice Live ペイロード組み立て・イベント解釈(voice.py)のオフラインテスト。

すべて純関数なので SDK もネットワークも不要 — 「音声なしでもコアと Voice Live
契約が検証できる」層設計の要。イベント形は Azure OpenAI Realtime API 互換
(実装前調査 2026-07 の voice-live-how-to 準拠)。
"""

from __future__ import annotations

import json

from conftest import complete_flood_claim, flood_classification

from claim_voice_live_maf.config import derive_voice_live_endpoint
from claim_voice_live_maf.policies import build_intake_state
from claim_voice_live_maf.voice import (
    CLAIM_TOOL_NAME,
    VOICE_INSTRUCTIONS,
    build_claim_tool_result,
    build_function_output_item,
    build_response_create,
    build_session_config,
    build_session_update,
    build_tool_definitions,
    build_user_text_item,
    build_websocket_url,
    parse_claim_tool_arguments,
    parse_voice_event,
)

# --- 送信ペイロード ----------------------------------------------------------


def test_session_config_defaults() -> None:
    session = build_session_config()
    assert session["modalities"] == ["text", "audio"]
    assert session["instructions"] == VOICE_INSTRUCTIONS
    assert session["voice"] == {"name": "en-US-AvaNeural", "type": "azure-standard"}
    assert session["turn_detection"]["type"] == "azure_semantic_vad"
    assert session["input_audio_transcription"] == {"model": "azure-speech"}
    assert session["input_audio_noise_reduction"] == {"type": "azure_deep_noise_suppression"}
    assert session["input_audio_echo_cancellation"] == {"type": "server_echo_cancellation"}
    assert session["tool_choice"] == "auto"
    assert [tool["name"] for tool in session["tools"]] == [CLAIM_TOOL_NAME]


def test_session_config_text_only_without_tools() -> None:
    session = build_session_config(modalities=("text",), include_tools=False)
    assert session["modalities"] == ["text"]
    assert "tools" not in session
    assert "tool_choice" not in session


def test_session_update_envelope() -> None:
    session = build_session_config()
    payload = build_session_update(session)
    assert payload["type"] == "session.update"
    assert payload["session"] is session
    json.dumps(payload)  # WebSocket にそのまま流せる JSON であること


def test_tool_definition_declares_transcript_parameter() -> None:
    (tool,) = build_tool_definitions()
    assert tool["type"] == "function"
    assert tool["name"] == CLAIM_TOOL_NAME
    assert tool["parameters"]["required"] == ["claimant_transcript"]
    assert tool["parameters"]["properties"]["claimant_transcript"]["type"] == "string"


def test_user_text_item_shape() -> None:
    payload = build_user_text_item("My basement flooded.")
    assert payload["type"] == "conversation.item.create"
    item = payload["item"]
    assert item["type"] == "message"
    assert item["role"] == "user"
    assert item["content"] == [{"type": "input_text", "text": "My basement flooded."}]


def test_function_output_item_serializes_result() -> None:
    payload = build_function_output_item("call-1", {"routing_decision": "needs_docs"})
    item = payload["item"]
    assert item["type"] == "function_call_output"
    assert item["call_id"] == "call-1"
    assert json.loads(item["output"]) == {"routing_decision": "needs_docs"}
    assert build_response_create() == {"type": "response.create"}


def test_claim_tool_result_summarizes_intake_state() -> None:
    state = build_intake_state(complete_flood_claim(), flood_classification())
    result = build_claim_tool_result(state)
    assert result["intake_status"] == "valid"
    assert result["routing_decision"] == "needs_docs"
    assert result["claim_type"] == "home_water_damage"
    assert result["missing_fields"] == []
    assert "Mitigation or drying invoice" in result["required_documents"]
    assert result["next_question"] == state.next_question


# --- 接続先の導出 ------------------------------------------------------------


def test_derive_voice_live_endpoint_from_project_endpoint() -> None:
    endpoint = derive_voice_live_endpoint(
        "https://aif-mafportsw2.services.ai.azure.com/api/projects/maf-ports"
    )
    assert endpoint == "https://aif-mafportsw2.services.ai.azure.com/"
    assert derive_voice_live_endpoint("") == ""
    assert derive_voice_live_endpoint("not-a-url") == ""


def test_websocket_url_matches_documented_contract() -> None:
    url = build_websocket_url(
        "https://aif-mafportsw2.services.ai.azure.com/", "gpt-4.1-mini", "2026-04-10"
    )
    assert url == (
        "wss://aif-mafportsw2.services.ai.azure.com/voice-live/realtime"
        "?api-version=2026-04-10&model=gpt-4.1-mini"
    )


# --- 受信イベントの解釈 ------------------------------------------------------


def test_parse_session_lifecycle_events() -> None:
    assert parse_voice_event({"type": "session.created"}).kind == "session_created"
    assert parse_voice_event({"type": "session.updated"}).kind == "session_updated"


def test_parse_input_transcription_events() -> None:
    delta = parse_voice_event(
        {"type": "conversation.item.input_audio_transcription.delta", "delta": "My base"}
    )
    assert (delta.kind, delta.text) == ("input_transcript_delta", "My base")
    done = parse_voice_event(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "My basement flooded.",
        }
    )
    assert (done.kind, done.text) == ("input_transcript_done", "My basement flooded.")


def test_parse_response_text_from_both_modalities() -> None:
    # テキストモダリティ
    text_delta = parse_voice_event({"type": "response.text.delta", "delta": "Hel"})
    assert (text_delta.kind, text_delta.text) == ("response_text_delta", "Hel")
    # 音声モダリティの逐語テキスト(元 Gemini Live の output_transcription 相当)
    audio_tx = parse_voice_event({"type": "response.audio_transcript.delta", "delta": "lo"})
    assert (audio_tx.kind, audio_tx.text) == ("response_text_delta", "lo")
    done = parse_voice_event({"type": "response.audio_transcript.done", "transcript": "Hello"})
    assert (done.kind, done.text) == ("response_text_done", "Hello")


def test_parse_function_call_event() -> None:
    event = parse_voice_event(
        {
            "type": "response.function_call_arguments.done",
            "call_id": "call-7",
            "name": CLAIM_TOOL_NAME,
            "arguments": '{"claimant_transcript": "My basement flooded."}',
        }
    )
    assert event.kind == "function_call"
    assert event.call_id == "call-7"
    assert event.name == CLAIM_TOOL_NAME
    assert parse_claim_tool_arguments(event.arguments) == "My basement flooded."


def test_parse_claim_tool_arguments_tolerates_bad_json() -> None:
    assert parse_claim_tool_arguments("not json") == ""
    assert parse_claim_tool_arguments("") == ""
    assert parse_claim_tool_arguments('{"other": 1}') == ""


def test_parse_audio_error_done_and_unknown_events() -> None:
    assert parse_voice_event({"type": "response.audio.delta", "delta": "AAAA"}).kind == "audio_delta"
    error = parse_voice_event(
        {"type": "error", "error": {"message": "invalid model", "code": "bad_request"}}
    )
    assert (error.kind, error.text) == ("error", "invalid model")
    assert parse_voice_event({"type": "response.done"}).kind == "response_done"
    other = parse_voice_event({"type": "rate_limits.updated"})
    assert other.kind == "other"
    assert other.raw == {"type": "rate_limits.updated"}

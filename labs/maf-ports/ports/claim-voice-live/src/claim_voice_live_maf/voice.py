"""Voice Live 層のペイロード組み立てと受信イベント解釈(すべて純関数)。

Gemini Live(元 live_demo/server.py)→ Azure Voice Live API の置換部分。
azure-ai-voicelive SDK の ``VoiceLiveConnection.send()`` は plain dict を
受けるため、送信ペイロードは SDK 型を使わず素の dict で組み立てる —
これで Voice Live 層の契約全体が SDK なし・ネットワークなしでテストできる。
実 WebSocket を貼るのは scripts/voice_session.py だけ。

実装前調査(2026-07、Learn: voice-live / voice-live-quickstart /
voice-live-how-to / regions?tabs=voice-live):

- SDK: ``azure-ai-voicelive``(PyPI 1.2.0、Python は安定版)。
  ``azure.ai.voicelive.aio.connect(credential=..., endpoint=..., model=...,
  api_version="2026-04-10")`` → WebSocket 接続。
- WebSocket 素の契約: ``wss://<res>.services.ai.azure.com/voice-live/realtime
  ?api-version=2026-04-10&model=<model>``。イベント体系は Azure OpenAI
  Realtime API 互換(session.update / conversation.item.create /
  response.create / response.* サーバイベント)。
- 認証: Entra(Bearer、scope ``https://ai.azure.com/.default``、要
  Cognitive Services User + Foundry User ロール)または api-key
  (接続ヘッダー or クエリ)。Foundry リソースの既存キーがそのまま使える。
- モデルは**マネージド提供**(デプロイ・容量計画不要)— survey features/07 の
  記述を overview 原文("you don't need to deploy or manage any generative
  AI models")で裏取り。例外: gpt-5.5 / gpt-5.4-mini / gpt-5.4-nano は
  pre-deploy されず BYOM が必要。
- リージョン: Japan East は Voice Live 対応。ただし **gpt-realtime 系
  (ネイティブ音声モデル)は Japan East 非提供** — gpt-4o / gpt-4.1 /
  gpt-5 系(音声入出力は Azure Speech の STT/TTS が担うモデル)を使う。
  既定は gpt-4.1-mini(config.py)。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .config import DEFAULT_VOICE_LIVE_VOICE
from .schemas import IntakeState

#: 元 server.py の Gemini Live system_instruction を移植し、FNOL コアを
#: 関数ツール(process_claim_turn)として使う指示を追記したもの。
VOICE_INSTRUCTIONS = (
    "You are a voice insurance FNOL intake agent. Speak naturally and briefly. "
    "Your job is to collect enough blocking intake facts for a smooth adjuster handoff, "
    "not to end the call after the claimant's first narrative. If injury, unsafe housing, "
    "or immediate danger is mentioned, prioritize safety and human escalation. Otherwise, "
    "keep asking for missing blockers one step at a time: claimant name, contact method, "
    "policy number if available, date and location of loss, what happened, safety/injury "
    "status, evidence, documents, reports, tow details, or other involved parties. Do not "
    "promise coverage, payment, liability, benefits, or approval. Ask only one or two "
    "focused follow-up questions at a time.\n\n"
    "After every claimant turn, call the process_claim_turn tool with everything the "
    "claimant has said so far. The tool runs the deterministic claim intake workflow and "
    "returns the current routing decision, missing facts, and the exact next question to "
    "ask. Ground your reply in the tool result: if it escalates, tell the claimant a human "
    "representative will take over; otherwise ask the returned next question in your own "
    "natural spoken words."
)

#: FNOL コアを Voice Live に見せる関数ツールの名前
CLAIM_TOOL_NAME = "process_claim_turn"


# --- 送信ペイロード(client events)----------------------------------------


def build_tool_definitions() -> list[dict[str, Any]]:
    """FNOL コア 1 本を Realtime API 互換の function ツールとして宣言する。"""
    return [
        {
            "type": "function",
            "name": CLAIM_TOOL_NAME,
            "description": (
                "Run the deterministic insurance claim intake workflow over the full "
                "claimant transcript so far. Returns intake status, routing decision, "
                "missing facts, and the next question to ask the claimant."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "claimant_transcript": {
                        "type": "string",
                        "description": (
                            "Everything the claimant has said so far in this call, "
                            "as one plain-text block."
                        ),
                    }
                },
                "required": ["claimant_transcript"],
            },
        }
    ]


def build_session_config(
    *,
    instructions: str = VOICE_INSTRUCTIONS,
    voice_name: str = DEFAULT_VOICE_LIVE_VOICE,
    modalities: tuple[str, ...] = ("text", "audio"),
    include_tools: bool = True,
    transcription_model: str = "azure-speech",
) -> dict[str, Any]:
    """session.update に載せる session オブジェクトを組み立てる。

    - voice: azure-standard(Japan East では gpt-realtime 系が使えないため、
      音声出力は常に Azure TTS 経由 — どのモデルでも同じ設定が通る)
    - turn_detection: azure_semantic_vad(Voice Live 固有の意味論 VAD。
      全モデルで利用可)
    - input_audio_transcription: azure-speech(非マルチモーダルモデルの既定。
      請求者発話のテキスト化 = FNOL コアへの入力を得る要)
    """
    session: dict[str, Any] = {
        "modalities": list(modalities),
        "instructions": instructions,
        "voice": {"name": voice_name, "type": "azure-standard"},
        "turn_detection": {"type": "azure_semantic_vad", "silence_duration_ms": 500},
        "input_audio_noise_reduction": {"type": "azure_deep_noise_suppression"},
        "input_audio_echo_cancellation": {"type": "server_echo_cancellation"},
        "input_audio_transcription": {"model": transcription_model},
    }
    if include_tools:
        session["tools"] = build_tool_definitions()
        session["tool_choice"] = "auto"
    return session


def build_session_update(session: dict[str, Any]) -> dict[str, Any]:
    return {"type": "session.update", "session": session}


def build_user_text_item(text: str) -> dict[str, Any]:
    """テキストターン(マイクなし環境・スモークの入力面)。"""
    return {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": text}],
        },
    }


def build_function_output_item(call_id: str, output: dict[str, Any]) -> dict[str, Any]:
    """ツール実行結果を会話へ返す(この後 response.create で応答を促す)。"""
    return {
        "type": "conversation.item.create",
        "item": {
            "type": "function_call_output",
            "call_id": call_id,
            "output": json.dumps(output, ensure_ascii=False),
        },
    }


def build_response_create() -> dict[str, Any]:
    return {"type": "response.create"}


def build_claim_tool_result(state: IntakeState) -> dict[str, Any]:
    """FNOL コアの実行結果を、音声エージェントが読める要約に落とす。"""
    return {
        "intake_status": state.validation.intake_status,
        "routing_decision": state.route,
        "claim_type": state.classification.claim_type,
        "severity": state.classification.severity,
        "missing_fields": state.validation.missing_fields,
        "required_documents": state.coverage.required_documents,
        "next_question": state.next_question,
    }


def build_websocket_url(endpoint: str, model: str, api_version: str) -> str:
    """素の WebSocket URL(ドキュメント用。実接続は SDK connect() が組み立てる)。"""
    host = endpoint.strip().removeprefix("https://").removeprefix("wss://").strip("/")
    return f"wss://{host}/voice-live/realtime?api-version={api_version}&model={model}"


# --- 受信イベントの解釈(server events)------------------------------------


@dataclass
class VoiceEvent:
    """アプリが関心を持つ範囲に正規化したサーバイベント。"""

    kind: str
    text: str = ""
    call_id: str = ""
    name: str = ""
    arguments: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


def parse_voice_event(payload: dict[str, Any]) -> VoiceEvent:
    """Voice Live のサーバイベント(JSON dict)を VoiceEvent に正規化する。

    イベント名は Azure OpenAI Realtime API 互換。音声出力の逐語テキストは
    テキストモダリティでは ``response.text.delta``、音声モダリティでは
    ``response.audio_transcript.delta`` に載るため、両方を response_text_delta
    に畳む(元 Gemini Live の output_transcription に対応)。
    """
    event_type = str(payload.get("type", ""))

    if event_type == "session.created":
        return VoiceEvent(kind="session_created", raw=payload)
    if event_type == "session.updated":
        return VoiceEvent(kind="session_updated", raw=payload)
    if event_type == "conversation.item.input_audio_transcription.delta":
        return VoiceEvent(
            kind="input_transcript_delta", text=str(payload.get("delta", "")), raw=payload
        )
    if event_type == "conversation.item.input_audio_transcription.completed":
        return VoiceEvent(
            kind="input_transcript_done", text=str(payload.get("transcript", "")), raw=payload
        )
    if event_type in ("response.text.delta", "response.audio_transcript.delta"):
        return VoiceEvent(
            kind="response_text_delta", text=str(payload.get("delta", "")), raw=payload
        )
    if event_type in ("response.text.done", "response.audio_transcript.done"):
        return VoiceEvent(
            kind="response_text_done",
            text=str(payload.get("text", payload.get("transcript", ""))),
            raw=payload,
        )
    if event_type == "response.audio.delta":
        return VoiceEvent(kind="audio_delta", raw=payload)
    if event_type == "response.function_call_arguments.done":
        return VoiceEvent(
            kind="function_call",
            call_id=str(payload.get("call_id", "")),
            name=str(payload.get("name", "")),
            arguments=str(payload.get("arguments", "")),
            raw=payload,
        )
    if event_type == "response.done":
        return VoiceEvent(kind="response_done", raw=payload)
    if event_type == "error":
        error = payload.get("error") or {}
        message = error.get("message", "") if isinstance(error, dict) else str(error)
        return VoiceEvent(kind="error", text=str(message), raw=payload)
    return VoiceEvent(kind="other", raw=payload)


def parse_claim_tool_arguments(arguments: str) -> str:
    """process_claim_turn の引数 JSON から claimant_transcript を取り出す。"""
    try:
        parsed = json.loads(arguments or "{}")
    except json.JSONDecodeError:
        return ""
    value = parsed.get("claimant_transcript", "") if isinstance(parsed, dict) else ""
    return str(value)

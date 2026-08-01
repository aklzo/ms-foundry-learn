"""E1: 音声エージェント / コンタクトセンター(08章)。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/e1-voice.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import BLUE, ORANGE, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "E1: Voice agent / contact center — Voice Live via ACS (SIP is not native)",
    width=1400,
    height=860,
    subtitle="Voice Live = managed speech-to-speech (STT + LLM + TTS + avatar in one API). "
    "Telephony arrives through Azure Communication Services, never directly.",
)

tel = d.cluster(40, 130, 250, 400, "Telephony", kind="external")
caller = d.node(140, 230, res("onprem/client/user.png"), "Caller",
                note="PSTN / SIP trunk / PBX")

azc = d.cluster(300, 110, 1360, 700, "Azure subscription", kind="azure")
acs = d.node(430, 280, az("general/mobile.png"), "ACS Call Automation",
             note="ACS number or Direct Routing (SIP)")
mid = d.node(650, 280, az("appservices/app-services.png"), "Your middle tier\n(server)",
             note="never client-direct in prod")

vl = d.cluster(790, 160, 1330, 600, "Voice Live API (Speech resource)", kind="sub",
               sublabel="Preview per GA table (2026-07)")
sess = d.node(890, 300, icon("speech"), "Voice Live\nsession",
              note="WebSocket (prod) / WebRTC (preview)")
stt = d.box(1130, 230, 170, 40, "STT (azure /\nwhisper / mai)")
llm = d.box(1130, 310, 170, 44, "LLM (gpt-realtime /\ngpt-5.x / phi4)")
tts = d.box(1130, 400, 170, 44, "TTS 600+ voices\n/ avatar (WebRTC)")
tools = d.box(1000, 510, 280, 40, "function calling / MCP / VoiceRAG")

d.edge(caller, acs, label="audio", label_t=0.5, label_dy=-14)
d.edge(acs, mid, label="bidirectional stream (WS)\nPCM 16/24kHz, 20ms", label_t=0.5, label_dy=-28)
d.edge(mid, sess, label="WebSocket\n+ Entra ID", label_color=BLUE, label_t=0.5, label_dy=-26)
d.edge(sess, stt, label="audio in", label_t=0.55, label_dy=-16)
d.edge(stt, llm)
d.edge(llm, tts)
d.edge(tts, sess, label="audio out", label_t=0.45, label_dy=18)

d.footer(
    notes=[
        "Sizing starts from quotas: max session 60 min / 30 new connections per min / "
        "TPM = NCPM x 4,000 -> contact-center scale ALWAYS needs a quota request.",
        "429 also fires while autoscale catches up -> exponential backoff mandatory "
        "(official ramp: +20 connections per 90-120s).",
        "Guardrails do NOT apply to voice models -> run Content Safety on the text path "
        "after STT. Semantic VAD supports Japanese; barge-in built in.",
    ],
    auth=[
        "Auth: Entra ID recommended (agent-connect mode REQUIRES Entra) / WebRTC is preview: "
        "keep production on WebSocket",
    ],
    config_note="Source: docs/survey/architecture/08 E1",
)

d.save(str(_here.parent.parent / "images" / "e1-voice.png"))

"""Architecture diagram for claim-voice-live (Port 12).

Regenerate:  uv run --with diagrams,pillow python ports/claim-voice-live/docs/architecture.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
for _p in _here.parents:
    if (_p / "tools" / "archdiagram.py").exists():
        sys.path.insert(0, str(_p / "tools"))
        break
from archdiagram import BLUE, F_EDGE, MUTED, ORANGE, TELEM, Diagram, icon  # noqa: E402

d = Diagram(
    "claim-voice-live — Voice Live FNOL intake (Port 12)",
    width=1400,
    height=860,
    subtitle="3 layers: voice-agnostic FNOL core (MAF workflow) / text CLI / Voice Live WebSocket — "
    "the core plugs into Voice Live as a function tool",
)

local = d.cluster(40, 100, 720, 650, "Local machine (uv + MAF)", kind="local")
l1 = d.cluster(70, 140, 700, 330, "Layer 1: FNOL core (MAF workflow, voice-agnostic)", kind="sub")
l2 = d.cluster(70, 360, 700, 460, "Layer 2: text CLI (main live-smoke path)", kind="sub")
l3 = d.cluster(70, 490, 700, 620, "Layer 3: voice (scripts/voice_session.py)", kind="sub")

stage_labels = ["extract*", "validate", "classify*", "rules", "checklist", "gate", "packet"]
stages = []
x = 150
for s in stage_labels:
    stages.append(d.box(x, 230, 82, 38, s, font=F_EDGE))
    x += 88
for a, b in zip(stages, stages[1:]):
    d.edge(a, b, width=1)
d.d.text((385, 280), "* = LLM stage (structured output); the other 5 are deterministic (policies.py)",
         font=F_EDGE, fill=MUTED, anchor="ma")

turn = d.box(385, 415, 560, 44, "turn loop: accumulate claimant transcript -> run core -> "
             "deterministic next question")
voice = d.box(385, 560, 590, 48, "WebSocket client: session.update (VAD, voice, tools) / text turns / "
              "process_claim_turn tool")

azure = d.cluster(760, 100, 1360, 720, "Azure subscription — rg-maf-ports (Japan East)", kind="azure")
foundry = d.cluster(790, 150, 1340, 560, "Foundry: aif-mafportsw2", kind="sub",
                    sublabel="shared infra (AIServices S0)")
vl = d.node(930, 400, icon("speech"), "Voice Live API\nmanaged gpt-4.1-mini")
model = d.node(1210, 260, icon("model"), "Model deployment\ngpt-5.4-mini", note="core LLM stages")
project = d.node(1210, 470, icon("project"), "Project: maf-ports")
appi = d.node(950, 645, icon("appinsights"), "App Insights\nappi-mafportsw2")
logw = d.node(1200, 645, icon("loganalytics"), "Log Analytics\nlog-mafportsw2")
d.edge(appi, logw)

d.edge(l2.port("top", 0.5), l1.port("bottom", 0.5), label="per turn", label_t=0.5, label_dx=44)
d.edge(l3.port("top", 0.25), l2.port("bottom", 0.25), label="tool call runs\nthe same core", label_t=0.5,
       label_dx=-62)
d.edge(l1.port("right", 0.5), model, label="extract + classify\n(response_format) / api-key",
       label_color=BLUE, label_t=0.45, label_dy=-28)
d.edge(vl.port("bottom", 0.75), voice.port("right", 0.85), via=[(760, 610)],
       label="audio + transcripts + function_call\n(process_claim_turn)", label_t=0.45, label_dx=70,
       label_dy=-10)
d.edge(voice.port("right", 0.35), vl.port("bottom", 0.35), via=[(740, 520), (905, 520)],
       label="wss /voice-live/realtime?api-version=2026-04-10\napi-key (Foundry resource key)",
       label_color=BLUE, label_t=0.6, label_dy=-26)
d.edge(local.port("right", 0.97), appi, style="dashed", color=TELEM,
       label="OTel traces", label_t=0.35, label_dy=-14)

d.footer(
    notes=[
        "Infra: no new ARM resources — Voice Live is the shared Foundry resource's data plane; models are "
        "managed service-side (no deployment, no capacity planning, no Bicep).",
        "$Voice Live billing: per-session tokens + audio (gpt-4.1-mini = basic price band). Region reality: "
        "Voice Live works in Japan East but the gpt-realtime family does not; gpt-5.4-mini would need BYOM.",
        "Lab constraint: no mic/speaker — live verification = WebSocket connect + text event round-trip + full "
        "tool loop (audio chunks received and discarded).",
    ],
    auth=[
        "Auth: Voice Live WS = api-key (Entra alternative needs Cognitive Services User + Foundry User) / core "
        "chat = api-key (OpenAI v1) / traces = App Insights connection string",
    ],
)

d.save(str(_here.parent / "architecture.png"))

"""Architecture diagram for travel-memory (Port 5).

Regenerate:  uv run --with diagrams,pillow python ports/travel-memory/docs/architecture.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
for _p in _here.parents:
    if (_p / "tools" / "archdiagram.py").exists():
        sys.path.insert(0, str(_p / "tools"))
        break
from archdiagram import BLUE, ORANGE, TELEM, Diagram, icon  # noqa: E402

d = Diagram(
    "travel-memory — chat with Foundry Memory (Port 5)",
    width=1400,
    height=850,
    subtitle="mem0 -> Foundry Memory store (public preview): explicit search -> inject -> respond -> "
    "update loop, scope = user_id",
)

local = d.cluster(40, 100, 720, 530, "Local machine (uv + MAF)", kind="local")
wf = d.cluster(170, 150, 700, 440, "Chat turn (run_turn, per user message)", kind="sub")

cli = d.node(100, 290, icon("cli"), "CLI\ntravel-memory-maf")
s1 = d.box(290, 220, 175, 44, "1. search_memories")
s2 = d.box(530, 220, 165, 44, "2. inject context\n(prompt header)")
s3 = d.box(530, 360, 165, 44, "3. travel_agent (LLM)")
s4 = d.box(290, 360, 195, 48, "4. update_memories x2\n(user + assistant, LRO)")
setup = d.box(430, 485, 370, 40, "scripts/setup_memory.py (create store, one-time)")

azure = d.cluster(760, 100, 1360, 695, "Azure subscription — rg-maf-ports (Japan East)", kind="azure")
foundry = d.cluster(780, 150, 1340, 498, "Foundry: aif-mafports", kind="sub",
                    sublabel="shared infra (AIServices S0)")
model = d.node(890, 225, icon("model"), "Model deployment\ngpt-5.4-mini")
embed = d.node(1105, 225, icon("model"), "Embedding deploy\ntext-emb-3-small")
project = d.node(1280, 225, icon("project"), "Project: maf-ports", note="system MI")
memory = d.node(1060, 400, icon("cache"), "Memory store (preview)\nscopes = user_id",
                note="data plane object — no ARM", note_color=ORANGE)
appi = d.node(1000, 600, icon("appinsights"), "App Insights\nappi-mafports")
logw = d.node(1230, 600, icon("loganalytics"), "Log Analytics\nlog-mafports")
d.edge(appi, logw)

d.edge(cli, s1, label="user message", label_dy=-14, label_t=0.6)
d.edge(s1, s2)
d.edge(s2, s3)
d.edge(s3, s4)

d.edge(wf.port("right", 0.22), model, label="chat (OpenAI v1)\napi-key", label_color=BLUE,
       label_t=0.4, label_dy=-24)
d.edge(wf.port("right", 0.75), memory,
       label="search / update (LRO, update_delay=0,\nchained update_id) — Entra ID only",
       label_color=BLUE, label_t=0.4, label_dy=30)
d.edge(setup, memory.port("bottom", 0.2), label="create store\nEntra ID", label_color=BLUE,
       label_t=0.6, label_dy=24)
d.edge(memory, embed, label="extraction +\nconsolidation\nproject MI (RBAC)", label_color=BLUE,
       label_t=0.35, label_dx=90)
d.edge(memory, model.port("bottom", 0.5), via=[(950, 345)])
d.edge(local.port("right", 0.93), appi, style="dashed", color=TELEM,
       label="OTel traces", label_t=0.45, label_dy=-14)

d.footer(
    notes=[
        "2-stage deploy: main.bicep has no new ARM resources (existing refs only) -> scripts/setup_memory.py "
        "creates the Memory store (data plane; references chat + embedding deployments).",
        "$Preview: billed as usage of the store's chat/embedding models (pricing may change during preview); "
        "no VNet support; LRO extraction ~1 min/turn (update_delay=0 + chained update_id).",
        "$RBAC gotcha (live-tested): Bicep-created project MI lacked OpenAI User role -> search_memories 401; "
        "fixed via roles.bicep 2nd stage, propagation took 5-7 min.",
    ],
    auth=[
        "Auth: chat model = api-key / Memory Store API = Entra ID only (DefaultAzureCredential, az login) / "
        "store-internal model calls = project MI + RBAC",
    ],
)

d.save(str(_here.parent / "architecture.png"))

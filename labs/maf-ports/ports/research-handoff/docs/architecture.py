"""Architecture diagram for research-handoff (Port 3).

Regenerate:  uv run --with diagrams,pillow python ports/research-handoff/docs/architecture.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
for _p in _here.parents:
    if (_p / "tools" / "archdiagram.py").exists():
        sys.path.insert(0, str(_p / "tools"))
        break
from archdiagram import BLUE, NOTE_SHARED_ONLY, TELEM, Diagram, icon, std_azure  # noqa: E402

d = Diagram(
    "research-handoff — triage + switch-case handoff (Port 3)",
    width=1400,
    height=790,
    subtitle="Handoff as data: TriageDecision (structured output) routed by add_switch_case_edge_group "
    "(no HandoffBuilder — see README)",
)

local = d.cluster(40, 100, 720, 500, "Local machine (uv + MAF)", kind="local")
wf = d.cluster(200, 150, 700, 480, "MAF workflow (switch-case edges)", kind="sub")
ext = d.cluster(40, 530, 430, 665, "External web (outside Azure)", kind="external")

cli = d.node(115, 280, icon("cli"), "CLI\nresearch-handoff-maf")
triage = d.box(320, 230, 170, 56, "triage\n(TriageDecision)")
research = d.box(320, 400, 190, 56, "research\n(search_web, save_fact)")
editor = d.box(590, 315, 150, 56, "editor\n(ResearchReport)")
ddg = d.node(200, 578, icon("browser"), "DuckDuckGo HTML", note="keyless HTTPS")

shared = std_azure(d, y1=660)

d.edge(cli, triage, label="topic", label_dy=-12)
d.edge(triage, research, label="Case:\nhandoff_to=research", label_t=0.5, label_dx=-68)
d.edge(triage, editor, label="Default: editor direct", label_t=0.55, label_dy=-12)
d.edge(research, editor, label="findings + facts\n(as prompt)", label_t=0.45, label_dy=24)
d.edge(research.port("bottom", 0.3), ddg, label="search_web", label_t=0.55, label_dx=-40)
d.edge(wf.port("right", 0.4), shared["model"], label="3x invoke_agent — chat +\nresponse_format / api-key",
       label_color=BLUE, label_t=0.4, label_dy=-26)
d.edge(local.port("right", 0.85), shared["appi"], style="dashed", color=TELEM,
       label="OTel traces +\nHandoffDecided events", label_t=0.5, label_dy=-6)

d.footer(
    notes=[
        NOTE_SHARED_ONLY,
        "$Billing: model tokens only — web search stays keyless DuckDuckGo (no Azure resource).",
    ],
    auth=[
        "Auth: model data plane = api-key (lab .env) / DuckDuckGo = none (keyless) / "
        "traces = App Insights connection string",
    ],
)

d.save(str(_here.parent / "architecture.png"))

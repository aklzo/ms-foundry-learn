"""Architecture diagram for services-agency (Port 13).

Regenerate:  uv run --with diagrams,pillow python ports/services-agency/docs/architecture.py
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
    "services-agency — communication-graph constraints (Port 13)",
    width=1400,
    height=840,
    subtitle="Agency Swarm port: LLM picks who to consult at runtime, allowed pairs only "
    "(agent-as-tool: talk_to_* generated per directed edge, replies return to the caller)",
)

local = d.cluster(40, 100, 720, 640, "Local machine (uv + MAF)", kind="local")
ag = d.cluster(210, 190, 700, 620, "Agency (agent-as-tool, depth cap 3, CommLog)", kind="sub")

cli = d.node(125, 380, icon("cli"), "CLI\nservices-agency-maf")
ceo = d.box(390, 240, 150, 52, "CEO\n(entry, 5 turns)")
cto = d.box(280, 400, 130, 48, "CTO")
pm = d.box(455, 400, 170, 48, "Product Manager")
dev = d.box(310, 545, 140, 48, "Developer")
cm = d.box(500, 545, 170, 48, "Client Manager")

shared = std_azure(d, base="mafportsw3", rg="rg-maf-ports-w3", y1=660)

d.edge(cli, ceo, label="project brief", label_t=0.3, label_dy=-16)
# 許可された有向エッジ = talk_to_* ツールの存在(7ペア)
d.edge(ceo.port("bottom", 0.25), cto, label="talk_to_*", label_color=BLUE, label_t=0.6, label_dx=-46)
d.edge(ceo.port("bottom", 0.75), pm)
d.edge(ceo.port("right", 0.5), cm.port("right", 0.2), via=[(700, 265), (700, 555)])
d.edge(ceo.port("left", 0.5), dev.port("left", 0.5), via=[(255, 265), (255, 560)])
d.edge(cto, dev)
d.edge(pm.port("bottom", 0.3), dev.port("top", 0.7))
d.edge(pm.port("bottom", 0.8), cm)
d.edge(ag.port("right", 0.3), shared["model"], label="invoke_agent per consult\napi-key", label_color=BLUE,
       label_t=0.45, label_dy=-26)
d.edge(local.port("right", 0.9), shared["appi"], style="dashed", color=TELEM,
       label="OTel: execute_tool talk_to_* >\ninvoke_agent nesting", label_t=0.7, label_dy=-30)

d.footer(
    notes=[
        NOTE_SHARED_ONLY,
        "Agency arrows = the 7 allowed directed pairs; a missing arrow means no talk_to_* tool exists "
        "(blocked at tool level). Depth cap 3 via ContextVar; every consult recorded in CommLog.",
    ],
    auth=[
        "Auth: model data plane = api-key (lab .env) / traces = App Insights connection string. "
        "No external services (all reasoning on the shared model).",
    ],
)

d.save(str(_here.parent / "architecture.png"))

"""Architecture diagram for mixture-of-agents (Port 2).

Regenerate:  uv run --with diagrams,pillow python ports/mixture-of-agents/docs/architecture.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
for _p in _here.parents:
    if (_p / "tools" / "archdiagram.py").exists():
        sys.path.insert(0, str(_p / "tools"))
        break
from archdiagram import BLUE, F_EDGE, MUTED, NOTE_SHARED_ONLY, TELEM, Diagram, icon, std_azure  # noqa: E402

d = Diagram(
    "mixture-of-agents — fan-out / fan-in (Port 2)",
    width=1400,
    height=790,
    subtitle="4 parallel proposer personas + aggregator on one shared model (self-MoA) — "
    "add_fan_out_edges / add_fan_in_edges",
)

local = d.cluster(40, 100, 720, 560, "Local machine (uv + MAF)", kind="local")
wf = d.cluster(200, 150, 700, 530, "MAF workflow (fan-out -> fan-in)", kind="sub")

cli = d.node(115, 330, icon("cli"), "CLI\nmixture-of-agents-maf")
disp = d.box(285, 340, 130, 50, "dispatcher\n(normalize)")
p1 = d.box(465, 215, 160, 40, "proposer: analyst")
p2 = d.box(465, 295, 160, 40, "proposer: creative")
p3 = d.box(465, 375, 160, 40, "proposer: skeptic")
p4 = d.box(465, 455, 160, 40, "proposer: pragmatist")
agg = d.box(630, 340, 110, 56, "aggregator\n(fan-in)")

shared = std_azure(d, y1=660)

d.edge(cli, disp, label="question", label_dy=-12)
for p in (p1, p2, p3, p4):
    d.edge(disp, p)
    d.edge(p, agg)
d.d.text((465, 495), "parallel (asyncio.gather), order = edge definition", font=F_EDGE, fill=MUTED, anchor="ma")

d.edge(wf.port("right", 0.35), shared["model"], label="5x invoke_agent — chat\napi-key",
       label_color=BLUE, label_t=0.4, label_dy=-26)
d.edge(local.port("right", 0.9), shared["appi"], style="dashed", color=TELEM,
       label="OTel traces (fan-out /\nfan-in edge spans)", label_t=0.5, label_dy=-6)

d.footer(
    notes=[
        NOTE_SHARED_ONLY + "  Default = self-MoA: one shared model x 4 personas.",
        "$Multi-model MoA (FOUNDRY_PROPOSER_MODELS=model-a,model-b,...) needs extra model deployments in "
        "shared.bicep — each deployment is a capacity + billing unit.",
    ],
    auth=[
        "Auth: model data plane = api-key (lab .env) / traces = App Insights connection string",
    ],
)

d.save(str(_here.parent / "architecture.png"))

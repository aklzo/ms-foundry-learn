"""Architecture diagram for game-design-team (Port 7).

Regenerate:  uv run --with diagrams,pillow python ports/game-design-team/docs/architecture.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
for _p in _here.parents:
    if (_p / "tools" / "archdiagram.py").exists():
        sys.path.insert(0, str(_p / "tools"))
        break
from archdiagram import BLUE, MUTED, NOTE_SHARED_ONLY, TELEM, Diagram, F_EDGE, icon, std_azure  # noqa: E402

d = Diagram(
    "game-design-team — deterministic ring, 2 laps (Port 7)",
    width=1400,
    height=790,
    subtitle="AG2 Swarm AfterWork ring -> explicit graph edges: lap 1 writes summaries, lap 2 writes "
    "'## X Design' sections (GameDesignContext as typed message)",
)

local = d.cluster(40, 100, 720, 560, "Local machine (uv + MAF)", kind="local")
wf = d.cluster(185, 150, 700, 530, "MAF workflow (ring + loop edge)", kind="sub")

cli = d.node(105, 300, icon("cli"), "CLI\ngame-design-team-maf")
story = d.box(265, 260, 105, 44, "story")
gameplay = d.box(390, 260, 105, 44, "gameplay")
visuals = d.box(525, 260, 105, 44, "visuals")
tech = d.box(645, 260, 90, 44, "tech")
deliver = d.box(450, 450, 190, 52, "deliver\n(GameDesignDocument)")

shared = std_azure(d, y1=660)

d.edge(cli, story, label="GameSpec\n(15 fields)", label_t=0.5, label_dy=-26)
d.edge(story, gameplay)
d.edge(gameplay, visuals)
d.edge(visuals, tech)
# loop edge tech -> story (Default case), routed under the row
d.edge(tech.port("bottom", 0.35), story.port("bottom", 0.5), via=[(625, 315), (265, 315)],
       label_t=0.5, label_dy=13, label="Default: next lap (switch-case)")
d.d.text((445, 380), "lap 1: 2-3 sentence summaries -> lap 2: detail sections (8 agent turns total)",
         font=F_EDGE, fill=MUTED, anchor="ma")
d.edge(tech, deliver, route="vh", label="Case: all four\nsections done", label_t=0.75, label_dx=64)

d.edge(wf.port("right", 0.3), shared["model"], label="8x invoke_agent — chat\napi-key",
       label_color=BLUE, label_t=0.4, label_dy=-26)
d.edge(local.port("right", 0.9), shared["appi"], style="dashed", color=TELEM,
       label="OTel traces (executor spans\nx2 per role = loop visible)", label_t=0.5, label_dy=-6)

d.footer(
    notes=[
        NOTE_SHARED_ONLY,
        "Role personas = static instructions; phase prompt (summary vs section) is rebuilt per run — "
        "no UPDATE_SYSTEM_MESSAGE machinery needed (stateless Agent.run).",
    ],
    auth=[
        "Auth: model data plane = api-key (lab .env) / traces = App Insights connection string",
    ],
)

d.save(str(_here.parent / "architecture.png"))

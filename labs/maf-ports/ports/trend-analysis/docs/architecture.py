"""Architecture diagram for trend-analysis (Port 1).

Regenerate:  uv run --with diagrams,pillow python ports/trend-analysis/docs/architecture.py
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
    "trend-analysis — sequential workflow (Port 1)",
    width=1400,
    height=790,
    subtitle="3-stage MAF WorkflowBuilder pipeline on the shared Foundry model (collect -> summarize -> analyze)",
)

local = d.cluster(40, 100, 720, 470, "Local machine (uv + MAF)", kind="local")
wf = d.cluster(210, 190, 695, 400, "MAF workflow (WorkflowBuilder, sequential)", kind="sub")
ext = d.cluster(40, 510, 430, 660, "External web (outside Azure)", kind="external")

cli = d.node(125, 290, icon("cli"), "CLI\ntrend-analysis-maf")
collect = d.box(300, 300, 140, 56, "collect\n(search_news)")
summarize = d.box(455, 300, 140, 56, "summarize\n(read_article)")
analyze = d.box(610, 300, 140, 56, "analyze\n(no tools)")
ddg = d.node(200, 570, icon("browser"), "DuckDuckGo HTML\n+ article sites", note="keyless HTTPS")

shared = std_azure(d, y1=660)

d.edge(cli, collect, label="topic", label_dy=-12)
d.edge(collect, summarize)
d.edge(summarize, analyze)
d.edge(wf.port("right", 0.5), shared["model"], label="3x invoke_agent — chat\napi-key", label_color=BLUE,
       label_t=0.4, label_dy=-26)
d.edge(collect.port("bottom", 0.3), ddg, label="search_news\n(DDG HTML)", label_t=0.55, label_dy=0, label_dx=-52)
d.edge(summarize.port("bottom", 0.7), ddg.port("right", 0.35), label="read_article\n(httpx + BS4)",
       label_t=0.5, label_dy=0, label_dx=44)
d.edge(local.port("right", 0.85), shared["appi"], style="dashed", color=TELEM,
       label="OTel traces (agent +\ntool-call spans)", label_t=0.45, label_dy=-4)

d.footer(
    notes=[
        NOTE_SHARED_ONLY,
        "$Billing: model tokens only — search stays keyless DuckDuckGo (no Azure search resource). "
        "Foundry web-search tool not used (extra billing, outside DPA).",
    ],
    auth=[
        "Auth: model data plane = api-key (lab .env) / DuckDuckGo + article fetch = none (keyless) / "
        "traces = App Insights connection string",
    ],
)

d.save(str(_here.parent / "architecture.png"))

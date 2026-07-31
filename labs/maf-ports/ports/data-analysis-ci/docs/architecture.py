"""Architecture diagram for data-analysis-ci (Port 8).

Regenerate:  uv run --with diagrams,pillow python ports/data-analysis-ci/docs/architecture.py
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
    "data-analysis-ci — Code Interpreter (Port 8)",
    width=1400,
    height=820,
    subtitle="Local DuckDB/pandas tools replaced by server-side Code Interpreter: CSV goes up via Files API, "
    "Python runs in an Azure sandbox",
)

local = d.cluster(40, 100, 660, 440, "Local machine (uv + MAF)", kind="local")

cli = d.node(120, 260, icon("cli"), "CLI\ndata-analysis-ci-maf")
upload = d.box(400, 190, 220, 52, "validate + upload data.csv\n(client keeps no pandas)")
agent = d.box(400, 350, 200, 56, "data_analyst (MAF Agent)\n+ code_interpreter dict")

azure = d.cluster(700, 100, 1360, 695, "Azure subscription — rg-maf-ports (Japan East)", kind="azure")
foundry = d.cluster(730, 150, 1330, 500, "Foundry: aif-mafportsw2", kind="sub",
                    sublabel="shared infra (AIServices S0)")
model = d.node(860, 285, icon("model"), "Model deployment\ngpt-5.4-mini", note="Responses API")
files = d.node(1070, 240, icon("files"), "Files API\n(purpose=assistants)")
project = d.node(1250, 240, icon("project"), "Project: maf-ports")
ci = d.node(1070, 400, icon("container"), "Code Interpreter session\n(sandbox container)",
            note="Hyper-V isolated, no egress, /mnt/data", note_color=ORANGE)
appi = d.node(950, 600, icon("appinsights"), "App Insights\nappi-mafportsw2")
logw = d.node(1200, 600, icon("loganalytics"), "Log Analytics\nlog-mafportsw2")
d.edge(appi, logw)

d.edge(cli, upload, label="data.csv", label_t=0.55, label_dy=-14)
d.edge(upload, agent, label="file-id +\nquestion", label_t=0.5, label_dx=-46)
d.edge(upload, files, label="files.create\napi-key", label_color=BLUE, label_t=0.45, label_dy=-24)
d.edge(agent, model, label="Responses API, tools=[code_interpreter]\napi-key", label_color=BLUE,
       label_t=0.45, label_dy=28)
d.edge(model, ci, label="runs generated Python (pandas);\nreturns code + logs + image URIs", label_t=0.5,
       label_dy=30, label_dx=-40)
d.edge(files, ci, label="container.file_ids ->\n/mnt/data/data.csv", label_t=0.5, label_dx=66)
d.edge(local.port("right", 0.9), appi, style="dashed", color=TELEM,
       label="OTel traces", label_t=0.4, label_dy=-14)

d.footer(
    notes=[
        "Infra: shared foundation only — the sandbox is service-provisioned, no ARM resource exists for it "
        "(billing without IaC footprint).",
        "$Code Interpreter: per-session billing (active 1 h / idle 30 min) on top of model tokens — every CLI run "
        "starts a container session.",
        "Data boundary: the CSV leaves the local machine (Files API upload) — residency/DPA consideration vs the "
        "original local DuckDB design.",
    ],
    auth=[
        "Auth: upload + Responses API = api-key on the OpenAI v1 endpoint (lab .env) / traces = App Insights "
        "connection string",
    ],
)

d.save(str(_here.parent / "architecture.png"))

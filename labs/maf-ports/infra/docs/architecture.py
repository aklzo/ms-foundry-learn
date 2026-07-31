"""Shared-infra architecture diagram (shared.bicep + roles.bicep).

Regenerate:  uv run --with diagrams,pillow python infra/docs/architecture.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
for _p in _here.parents:
    if (_p / "tools" / "archdiagram.py").exists():
        sys.path.insert(0, str(_p / "tools"))
        break
from archdiagram import BLUE, F_EDGE, MUTED, TELEM, Diagram, icon  # noqa: E402

d = Diagram(
    "maf-ports shared infra — Foundry + monitoring",
    width=1400,
    height=820,
    subtitle="infra/shared.bicep (deploy once, all 12 ports) + infra/roles.bicep (2nd stage: RBAC for MIs)",
)

# --- clusters ---------------------------------------------------------------
local = d.cluster(40, 110, 360, 480, "Local machine (uv + MAF)", kind="local")
azure = d.cluster(420, 100, 1360, 660, "Azure subscription — rg-maf-ports (Japan East)", kind="azure")
foundry = d.cluster(
    460, 150, 1010, 420, "Foundry account: aif-mafports", kind="sub",
    sublabel="kind AIServices, SKU S0, public network, local auth on, system MI",
)

# --- nodes ------------------------------------------------------------------
cli = d.node(140, 220, icon("cli"), "MAF port CLIs\n(ports/*, Python)", note="OTel: configure_azure_monitor")
azcli = d.node(258, 395, icon("cli"), "az CLI + Bicep", note="shared.bicep -> roles.bicep")

project = d.node(600, 280, icon("project"), "Project: maf-ports", note="system-assigned MI")
model = d.node(880, 280, icon("model"), "Model deployment\ngpt-5.4-mini", note="GlobalStandard, capacity 10")

rbac = d.node(
    1200, 230, icon("rbac"),
    "roles.bicep\n4 role assignments",
    note="OpenAI User + Foundry User",
)
d.d.text((1200, rbac.y1 + 2), "x (account MI, project MI)", font=F_EDGE, fill=MUTED, anchor="ma")

appi = d.node(640, 560, icon("appinsights"), "App Insights\nappi-mafports")
logws = d.node(950, 560, icon("loganalytics"), "Log Analytics\nlog-mafports", note="PerGB2018, 30 days")

# --- edges ------------------------------------------------------------------
d.edge(cli, model, label="chat (OpenAI v1 endpoint)\napi-key", label_color=BLUE, label_t=0.42)
d.edge(cli, project, label="project endpoint (data plane)\nEntra ID (az login)", label_color=BLUE,
       label_t=0.62, label_dy=26)
d.edge(azcli, (azure.x0, 395), label="ARM deploy (2-stage)", label_t=0.55, label_dy=-14)
d.edge(rbac, foundry.port("right", 0.8), label="grants data-plane roles\n(scope: account)", label_t=0.75, label_dy=26)
d.edge(project, appi, label="AppInsights connection\n(connection string, shared to all)", label_t=0.5,
       label_dx=8, label_dy=0)
d.edge(appi, logws, label="workspace-based")
d.edge(cli, appi, style="dashed", color=TELEM, label="OTel traces", route="vh", label_t=0.45, label_dy=-12)

# --- footer -----------------------------------------------------------------
d.footer(
    notes=[
        "2-stage deploy: 1) shared.bicep (account + project + model + monitoring)   "
        "2) roles.bicep with MI principalIds as params (guid seed includes pid -> survives MI rotation, no orphan assignments)",
        "$Billing: model tokens (GlobalStandard) + App Insights / Log Analytics ingestion. "
        "RG deleted 2026-07-31 after validation — redeploy with a new RG name (stateless design).",
    ],
    auth=[
        "Auth map: model data plane = api-key (lab default) / project data plane = Entra ID / "
        "service-side features (Memory, evals) = account & project MI + roles.bicep RBAC",
    ],
)

d.save(str(_here.parent / "architecture.png"))

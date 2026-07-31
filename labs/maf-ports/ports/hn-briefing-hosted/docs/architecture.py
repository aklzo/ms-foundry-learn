"""Architecture diagram for hn-briefing-hosted (Port 11).

Regenerate:  uv run --with diagrams,pillow python ports/hn-briefing-hosted/docs/architecture.py
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
    "hn-briefing-hosted — hosted agent + Routines (Port 11)",
    width=1400,
    height=850,
    subtitle="The only port that runs IN Foundry: agent executes in a managed container; the always-on glue "
    "(scheduler, HTTP server, auth) moves to the platform",
)

local = d.cluster(40, 100, 380, 430, "Local machine (deploy only)", kind="local")
op = d.node(110, 185, icon("user"), "Operator\n(az login)")
deploy = d.box(215, 300, 290, 48, "hosting/deploy_hosted_agent.py\n(zip: main.py + requirements.txt)")
routset = d.box(200, 385, 260, 40, "scripts/setup_routine.py (REST)")

ext = d.cluster(40, 470, 380, 650, "External web (outside Azure)", kind="external")
hn = d.node(170, 545, icon("browser"), "HN Algolia API\n(front-page JSON)", note="keyless HTTPS")

azure = d.cluster(440, 100, 1360, 720, "Azure subscription — rg-maf-ports (Japan East)", kind="azure")
foundry = d.cluster(470, 150, 1330, 560, "Foundry: aif-mafportsw2", kind="sub",
                    sublabel="shared infra (AIServices S0)")
routine = d.node(590, 335, icon("scheduler"), "Routine (preview)\ncron weekdays 21:00 JST",
                 note="disabled after validation", note_color=ORANGE)
hosted = d.node(890, 260, icon("containerapp"), "Hosted agent: hn-briefing\nResponsesHostServer (:8088)",
                note="per-session sandbox, $HOME persisted")
tool = d.box(890, 445, 280, 52, "function tool: collect_ranked_stories\n(in-container httpx -> deterministic rank)")
model = d.node(1200, 260, icon("model"), "Model deployment\ngpt-5.4-mini")
project = d.node(1200, 445, icon("project"), "Project: maf-ports")
appi = d.node(700, 640, icon("appinsights"), "App Insights\nappi-mafportsw2")
logw = d.node(1000, 640, icon("loganalytics"), "Log Analytics\nlog-mafportsw2")
d.edge(appi, logw)

d.edge(op, deploy)
d.edge(op, routset, via=[(62, 250), (62, 385)])
d.edge(deploy, hosted.port("left", 0.15), via=[(620, 238)],
       label="SDK create_version_from_code\n(REMOTE_BUILD) — Entra ID", label_color=BLUE,
       label_t=0.4, label_dy=-28)
d.edge(routset, routine.port("left", 0.5),
       label="PUT /routines?api-version=v1\n+ Foundry-Features header — Entra ID", label_color=BLUE,
       label_t=0.55, label_dy=34, label_dx=-30)
d.edge(routine, hosted, label="invoke_agent_responses_api\n(1 trigger + 1 action)", label_t=0.5, label_dy=-28)
d.edge(hosted, model, label="FoundryChatClient —\nagent identity (Entra ID)", label_color=BLUE,
       label_t=0.5, label_dy=-26)
d.edge(hosted, tool, label="tool call", label_t=0.5, label_dx=32)
d.edge(tool.port("left", 0.5), hn.port("right", 0.3), label="HTTPS GET (keyless)", label_t=0.45, label_dy=-14)
d.edge(hosted, appi, style="dashed", color=TELEM, via=[(680, 340), (680, 560)],
       label="OTel auto — conn string\ninjected by platform", label_t=0.6, label_dy=0, label_dx=-100)

d.footer(
    notes=[
        "Hosted agent + Routine are data-plane objects with no ARM type: Bicep stays existing-refs-only, deploy "
        "is script-driven (zip -> REMOTE_BUILD -> version -> 100% routing; versions are immutable).",
        "$Billing: active-session CPU/mem (0.5 vCPU / 1 GiB) + tokens; scale-to-zero after 15 min idle; each cron "
        "fire pays a cold start. Routine left disabled to avoid unattended spend.",
        "'No tool attach' constraint is about Foundry-managed tools only — this in-container httpx function tool "
        "needed no Toolbox (proven live).",
    ],
    auth=[
        "Auth: model = agent identity (dedicated Entra ID, zero secrets in container) / deploy + routine "
        "management = Entra ID (az login, Foundry Project Manager) / HN Algolia = keyless",
    ],
)

d.save(str(_here.parent / "architecture.png"))

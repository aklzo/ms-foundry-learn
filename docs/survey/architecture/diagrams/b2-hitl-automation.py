"""B2: 承認付き業務自動化 HITL(05章)のアーキテクチャ図。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/b2-hitl-automation.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import BLUE, ORANGE, TELEM, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "B2: Approval-gated automation (HITL) — MAF hosted agent",
    width=1400,
    height=900,
    subtitle="Agent investigates -> proposes action -> human approves -> execute -> audit. "
    "Prompt agents cannot express this: branch / wait / resume => code-first.",
)

# --- client side -------------------------------------------------------------
cli = d.cluster(40, 130, 300, 430, "Business channel", kind="external")
teams = d.node(170, 230, res("saas/chat/teams.png"), "Business UI /\nTeams")
user = d.node(170, 360, res("onprem/client/user.png"), "Approver")
d.edge(user, teams)

# --- Azure -------------------------------------------------------------------
azc = d.cluster(350, 110, 1360, 720, "Azure subscription", kind="azure")
fc = d.cluster(380, 160, 1130, 560, "Foundry", kind="sub")

ha = d.cluster(410, 210, 900, 530, "Hosted agent (MAF, Responses protocol)", kind="sub",
               sublabel="sizes: 0.5/1/2 vCPU - billed per active session")
hosted = d.node(490, 300, icon("containerapp"), "Hosted agent\ncontainer", note="Entra Agent ID")
triage = d.box(660, 260, 110, 40, "triage")
research = d.box(800, 260, 110, 40, "research\n(RAG)")
proposal = d.box(800, 340, 110, 40, "action\nproposal")
hitl = d.box(660, 340, 120, 44, "RequestInfo\nExecutor (HITL)")
execute = d.box(660, 430, 110, 40, "execute\n(tools)")
audit = d.box(800, 430, 110, 40, "audit\nrecord")
d.edge(triage, research)
d.edge(research, proposal)
d.edge(proposal, hitl, label="approve?", label_t=0.5, label_dy=14)
d.edge(hitl, execute, label="approved", label_t=0.5, label_dx=-40)
d.edge(execute, audit)

model = d.node(1010, 300, icon("model"), "Model\ndeployment")
appi = d.node(1010, 450, icon("appinsights"), "App Insights",
              note="connection string auto-injected")

apim = d.node(1230, 300, az("integration/api-management.png"),
              "APIM / Toolbox\n(MCP)", note="tool governance")

# --- LOB ---------------------------------------------------------------------
lob = d.cluster(1180, 480, 1360, 690, "Line-of-business", kind="external")
erp = d.node(1270, 570, icon("browser"), "Core systems /\nLogic Apps connectors")

# --- edges -------------------------------------------------------------------
d.edge(teams, hosted, label="Responses API", label_t=0.45, label_dy=-14)
d.edge(hitl.port("left", 0.5), (310, 362), arrow=False, color=BLUE)
d.edge((310, 362), user, label="approval request /\ndecision", label_color=BLUE, label_t=0.4,
       label_dy=-26, color=BLUE)
d.edge(ha.port("right", 0.25), model, label="chat + tool calls", label_t=0.4, label_dy=-12)
d.edge(execute, apim, via=[(660, 610), (1230, 610)], label="MCP tool calls",
       label_t=0.5, label_dy=-14)
d.edge(apim, erp)
d.edge(ha.port("right", 0.75), appi, style="dashed", color=TELEM,
       label="OTel traces\n(default on)", label_t=0.3, label_dy=-26)

d.footer(
    notes=[
        "Idle 15 min = compute deprovision (state kept) / 30 days inactive = permanent delete. "
        "Multi-day approvals -> B3 (Durable Extension + DTS).",
        "Tracing is NOT the business audit log: 90-day portal window, traces may carry prompts/PII, "
        "no VNet support -> keep who/when/what-approved in your own store (MAF middleware).",
        "$Billing = CPU + memory of all active sessions; oversizing multiplies by concurrency. "
        "MAF Graph API is the supported surface (Functional API is experimental).",
    ],
    auth=[
        "Auth: approver -> business UI (Entra ID) / hosted agent -> Entra Agent ID (per-agent, not shared) / "
        "LOB tools -> APIM: decide OBO vs app-only per tool",
    ],
    config_note="Source: docs/survey/architecture/05 B2",
)

d.save(str(_here.parent.parent / "images" / "b2-hitl-automation.png"))

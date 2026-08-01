"""B4: マルチエージェント(専門分化、05章)。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/b4-multi-agent.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import BLUE, ORANGE, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "B4: Multi-agent with domain specialization — MAF workflow + hosted agents",
    width=1400,
    height=880,
    subtitle="Only when per-domain prompts / knowledge / PERMISSIONS must differ, or parallel "
    "research pays. Single agent + tools is enough for most cases (-> ch.11).",
)

user = d.node(130, 260, res("onprem/client/user.png"), "User / app")

azc = d.cluster(280, 110, 1340, 740, "Azure subscription", kind="azure")
fc = d.cluster(310, 160, 1020, 710, "Foundry", kind="sub")

wf = d.node(440, 290, icon("workflow"), "MAF workflow\n(orchestrator, code)",
            note="all 5 patterns built-in")
a1 = d.node(730, 230, icon("containerapp"), "Research agent",
            note="own Entra Agent ID + knowledge", note_color=BLUE)
a2 = d.node(730, 410, icon("containerapp"), "Ops agent",
            note="own tools + RBAC scope", note_color=BLUE)
a3 = d.node(730, 590, icon("containerapp"), "Compliance agent",
            note="read-only knowledge", note_color=BLUE)
model = d.node(920, 410, icon("model"), "Model\ndeployment(s)", note="size per agent task")

ext = d.cluster(1090, 200, 1340, 450, "Partner / other org", kind="external")
pa = d.node(1215, 300, icon("project"), "External agent",
            note="A2A: text-only, no SSE (preview)")

d.edge(user, wf)
d.edge(wf, a1, label="sequential / concurrent /\nhandoff / group chat / magentic",
       label_t=0.45, label_dy=-30)
d.edge(wf, a2)
d.edge(wf, a3)
d.edge(a2, model, label="each agent -> model\n(size per task)", label_t=0.5, label_dy=-28)
d.edge(a1, pa, label="A2A (Entra required)", label_color=BLUE, label_t=0.55, label_dy=-16)

d.footer(
    notes=[
        "Portal visual Workflows retire 2026-12-01 -> MAF (code, recommended) / Logic Apps (visual) / "
        "A2A (simple delegation). Export the YAML before the designer disappears.",
        "Prompt agents SHARE one identity per project -> per-agent permissions & audit need hosted "
        "agents (each gets its own Entra Agent ID) or separate projects.",
        "Security trimming must be implemented in EVERY agent (official). Anti-patterns: agents "
        "without real specialization, shared mutable state between parallel agents.",
    ],
    auth=[
        "Auth: per-agent Entra Agent ID = least privilege per domain / A2A callers need "
        "Foundry Agent Consumer role, key auth impossible",
    ],
    config_note="Source: docs/survey/architecture/05 B4 (pattern selection: ch.11)",
)

d.save(str(_here.parent.parent / "images" / "b4-multi-agent.png"))

"""B5: 業務フローエンジン主導(Logic Apps / Copilot Studio、05章)。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/b5-flow-engine.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import BLUE, ORANGE, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "B5: Business-flow engine in charge — Logic Apps / Copilot Studio + Foundry as a component",
    width=1400,
    height=800,
    subtitle="Approvals, notifications and SaaS integration are the main flow; AI handles part of "
    "the judgement. Business departments maintain the flow themselves.",
)

biz = d.node(130, 260, res("onprem/client/user.png"), "Business dept",
             note="maintains the flow (no-code)")

azc = d.cluster(280, 110, 1340, 650, "Azure subscription", kind="azure")

la = d.cluster(310, 160, 760, 500, "Logic Apps — the main engine", kind="sub")
loop = d.node(430, 270, az("integration/logic-apps.png"), "Agent loop workflow",
              note="autonomous / conversational")
conn = d.box(430, 420, 250, 48, "1,400+ connectors\n(approvals / SaaS / notify)")

cs = d.node(620, 570, icon("workflow"), "Copilot Studio agent",
            note="SaaS side, business-owned")

fc = d.cluster(850, 160, 1310, 620, "Foundry — the hard 20%", kind="sub")
agent = d.node(960, 270, icon("project"), "Foundry agent",
               note="model source for agent loop")
model = d.node(1180, 270, icon("model"), "Model\ndeployment")
hosted = d.node(960, 480, icon("containerapp"), "Hosted agent\n(complex logic)",
                note="connected-agent target")

d.edge(biz, loop)
d.edge(loop, conn)
d.edge(loop, agent, label="model source\n(managed identity)", label_color=BLUE,
       label_t=0.45, label_dy=-26)
d.edge(agent, loop, label="call workflow\nas an action", label_t=0.55, label_dy=26,
       via=[(805, 340)])
d.edge(cs, hosted, label="connected agent (preview,\nnew-portal agents only)", label_color=BLUE,
       label_t=0.5, label_dy=26)
d.edge(agent, model)

d.footer(
    notes=[
        "CAF: low-code SaaS development opens building to business users BUT heavy customization "
        "hits its limit and forces replatforming -> if complexity is already visible, don't start here.",
        "Direction matters: Copilot Studio -> Foundry connection is PREVIEW; "
        "Foundry -> M365 Copilot / Teams publish is GA.",
        "Foundry agent can also call Logic Apps workflows as actions (reverse direction) - "
        "the two engines compose both ways.",
    ],
    auth=[
        "Auth: Logic Apps -> Foundry via managed identity / Copilot Studio connection scoped per agent",
    ],
    config_note="Source: docs/survey/architecture/05 B5 (platform choice: ch.11)",
)

d.save(str(_here.parent.parent / "images" / "b5-flow-engine.png"))

"""E5: M365 / Teams 連携(08章)。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/e5-m365-channels.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import BLUE, ORANGE, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "E5: Publishing agents to Teams / M365 Copilot",
    width=1400,
    height=820,
    subtitle="Foundry -> M365/Teams publish is GA (Activity protocol auto-bridged from Responses). "
    "The reverse direction - Copilot Studio consuming Foundry agents - is preview.",
)

azc = d.cluster(60, 130, 560, 420, "Azure subscription", kind="azure")
agent = d.node(180, 260, icon("project"), "Foundry agent\n(Prompt / Hosted)",
               note="stable endpoint")
bot = d.node(420, 260, az("aimachinelearning/bot-services.png"), "Bot Service",
             note="Activity protocol bridge")

m365 = d.cluster(620, 130, 1080, 420, "Microsoft 365", kind="external")
teams = d.node(740, 260, res("saas/chat/teams.png"), "Teams / M365 Copilot\nagent store",
               note="M365 admin approval required")
users = d.node(970, 260, res("onprem/client/users.png"), "End users",
               note="publisher-pays billing", note_color=ORANGE)

csc = d.cluster(620, 460, 1080, 660, "Copilot Studio (SaaS)", kind="external")
cs = d.node(800, 550, icon("workflow"), "Copilot Studio agent",
            note="business-owned entry point")

d.edge(agent, bot, label="Teams app manifest", label_t=0.5, label_dy=-14)
d.edge(bot, teams)
d.edge(teams, users)
d.edge(cs, agent, label="connected agent (preview,\nnew-portal agents only)", label_color=BLUE,
       label_t=0.55, label_dy=26, via=[(400, 550)])

d.footer(
    notes=[
        "Closed-network projects cannot publish from the portal (REST only). Azure Government: "
        "publish unsupported. Legacy Agent Applications format cannot be newly published.",
        "Auth has 2 modes: OAuth OBO (user token) or the agent's own identity "
        "(autonomous / background). Work IQ adds M365 context but needs Global Admin consent + license.",
        "Full multi-channel control (Teams + web + custom apps) -> M365 Agents SDK, which can "
        "embed MAF as its orchestrator.",
    ],
    config_note="Source: docs/survey/architecture/08 E5",
)

d.save(str(_here.parent.parent / "images" / "e5-m365-channels.png"))

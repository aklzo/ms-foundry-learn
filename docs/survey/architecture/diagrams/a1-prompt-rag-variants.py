"""A1/A3/A4: Prompt agent + マネージドナレッジ 3 変種(04章)。同一骨格のため 1 枚に統合。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/a1-prompt-rag-variants.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import BLUE, ORANGE, TELEM, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "A1 / A3 / A4: Prompt agent + managed knowledge — same shape, three knowledge choices",
    width=1400,
    height=800,
    subtitle="The smallest managed configs. Escalate to A2 (own index) when per-user visibility, "
    "metadata filters, xlsx, or closed network enter the requirements.",
)

user = d.node(120, 250, res("onprem/client/user.png"), "User", note="Entra ID sign-in")
appsvc = d.node(320, 250, az("appservices/app-services.png"), "App Service /\nweb app",
                note="managed identity")

azc = d.cluster(480, 110, 1360, 660, "Azure subscription", kind="azure")
fc = d.cluster(510, 160, 880, 480, "Foundry", kind="sub")
agent = d.node(610, 260, icon("project"), "Prompt agent\n(project)")
model = d.node(790, 260, icon("model"), "Model\ndeployment")
appi = d.node(700, 405, icon("appinsights"), "App Insights\n(traces)")

k1 = d.node(1090, 210, icon("files"), "A1: File Search vector store",
            note="defaults: chunk 800 tok / 3-large@256dim")
k2 = d.node(1090, 385, icon("search"), "A3: AI Search tool\n(existing index)",
            note="1 index only / same tenant")
k3 = d.node(1090, 555, icon("files"), "A4: SharePoint tool\n(M365 Retrieval API)",
            note="native permission trimming", note_color=BLUE)

d.edge(user, appsvc)
d.edge(appsvc, agent, label="Responses", label_t=0.5, label_dy=-14)
d.edge(agent, model)
d.edge(agent, appi, style="dashed", color=TELEM)
d.edge(agent, k1, label="hybrid + rerank\n(built-in)", label_t=0.55, label_dy=-26)
d.edge(agent, k2, label="project MI", label_color=BLUE, label_t=0.55, label_dy=-14)
d.edge(agent, k3, label="OBO only\n(no app-only)", label_color=BLUE, label_t=0.5, label_dy=22)

d.footer(
    notes=[
        "A1 dead-ends (check first): no doc-level ACL / no metadata filter / no xlsx-csv / "
        "not available in closed network -> any of these means A2.",
        "A3: agent evaluators (groundedness, tool_call_accuracy...) are officially unusable with "
        "the AI Search tool -> CI evals need A5 (MCP) or your own harness.",
        "$A1 cost = tokens + vector storage GB/day. A4 needs M365 Copilot license (or Retrieval API "
        "pay-as-you-go) for devs AND end users; not usable from Teams-published agents.",
    ],
    auth=[
        "Auth: user -> Entra ID / A3 tool -> project managed identity (key auth impossible in private VNet) / "
        "A4 -> OBO only: batch and autonomous agents cannot use it",
    ],
    config_note="Source: docs/survey/architecture/04 A1, A3, A4",
)

d.save(str(_here.parent.parent / "images" / "a1-prompt-rag-variants.png"))

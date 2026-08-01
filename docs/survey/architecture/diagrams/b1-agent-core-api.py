"""B1: 単一エージェント + 基幹 API(05章)。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/b1-agent-core-api.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import BLUE, ORANGE, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "B1: Single agent + line-of-business APIs (read-mostly)",
    width=1400,
    height=860,
    subtitle="Inventory / order-status / customer lookups. The real design work is authorization: "
    "app-only (agent identity) vs on-behalf-of (user permissions).",
)

user = d.node(130, 250, res("onprem/client/user.png"), "User\n(Teams / portal)", note="Entra ID")

azc = d.cluster(280, 110, 1060, 720, "Azure subscription", kind="azure")
fc = d.cluster(310, 160, 1030, 350, "Foundry", kind="sub")
agent = d.node(430, 250, icon("project"), "Prompt agent", note="publish -> dedicated agent identity")
model = d.node(620, 250, icon("model"), "Model\ndeployment")
guard = d.box(850, 250, 210, 52, "Guardrails at tool call +\ntool response (preview)")

tb = d.cluster(310, 390, 1030, 680, "Toolbox — single MCP-compatible endpoint", kind="sub",
               sublabel="versioning + central auth")
t1 = d.box(450, 480, 220, 48, "OpenAPI tool (GA)\nkey / managed identity")
t2 = d.box(720, 480, 230, 48, "MCP tool (GA)\nEntra / OAuth ID passthrough")
t3 = d.box(450, 590, 220, 48, "Azure Functions (GA)\nstandard setup only")
t4 = d.box(720, 590, 230, 48, "AI Search\n(manuals / master data)")

lob = d.cluster(1120, 260, 1360, 680, "Line-of-business", kind="external")
apim = d.node(1240, 350, az("integration/api-management.png"), "APIM\n(internal)")
core = d.node(1240, 500, icon("browser"), "Core systems API")
saas = d.node(1240, 620, icon("browser"), "SaaS\n(ServiceNow etc.)")

d.edge(user, agent, label="Entra ID", label_color=BLUE, label_t=0.5, label_dy=-14)
d.edge(agent, model)
d.edge(agent, tb.port("top", 0.3), label="tool calls", label_t=0.5, label_dx=48)
d.edge(t1, apim, label="managed identity", label_color=BLUE, label_t=0.35, label_dy=-16,
       via=[(1080, 430)])
d.edge(apim, core)
d.edge(t2, saas, label="OAuth OBO", label_color=BLUE, label_t=0.45, label_dy=18)

d.footer(
    notes=[
        "Hosted agents cannot attach tools directly (official) -> build on Toolbox from day one "
        "if code-first is on the roadmap. Runtime tool overrides allow one agent def across dev/stg/prod.",
        "Write operations: idempotency keys + server-side amount/permission limits IN the tool "
        "('ask approval above 100k JPY' in the prompt is not a control).",
        "Logic Apps connector -> MCP conversion is preview: managed connectors only, no OAuth 2.0 connectors.",
    ],
    auth=[
        "Auth: attended = OBO / unattended = agent identity RBAC. Principal = agent identity "
        "(NOT project MI); audience = downstream resource ID; prod credential = federated",
    ],
    config_note="Source: docs/survey/architecture/05 B1",
)

d.save(str(_here.parent.parent / "images" / "b1-agent-core-api.png"))

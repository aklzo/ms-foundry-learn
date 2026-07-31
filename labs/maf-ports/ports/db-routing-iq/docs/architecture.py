"""Architecture diagram for db-routing-iq (Port 10).

Regenerate:  uv run --with diagrams,pillow python ports/db-routing-iq/docs/architecture.py
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
    "db-routing-iq — Foundry IQ agentic retrieval (Port 10)",
    width=1400,
    height=880,
    subtitle="The app-side 3-stage routing cascade becomes a knowledge base property: KS x3 -> KB -> "
    "MCP endpoint on AI Search Basic",
)

local = d.cluster(40, 100, 680, 470, "Local machine (uv + MAF)", kind="local")
ext = d.cluster(40, 510, 360, 660, "External web (outside Azure)", kind="external")

cli = d.node(110, 220, icon("cli"), "CLI\ndb-routing-iq-maf")
agent = d.box(330, 210, 180, 56, "db_routing_agent\n(MAF Agent)")
mcp = d.box(480, 320, 230, 56, "MCPStreamableHTTPTool\nknowledge_base_retrieve")
web = d.box(210, 330, 170, 44, "web_search (DDG)\nfallback tool")
setup = d.box(330, 425, 280, 38, "scripts/setup_kb.py (one-time, REST)")
ddg = d.node(170, 578, icon("browser"), "DuckDuckGo HTML", note="keyless HTTPS")

azure = d.cluster(720, 100, 1360, 750, "Azure subscription — rg-maf-ports (Japan East)", kind="azure")
srch = d.cluster(750, 150, 1340, 430, "AI Search: srch-mafportsw2-iq — Basic SKU", kind="sub",
                 sublabel="agentic retrieval (Foundry IQ)")
sicon = d.node(830, 250, icon("search"), "search service\nBasic (1 replica)", note="~$0.10/h",
               note_color=ORANGE)
idx = d.box(1000, 240, 150, 56, "indexes x3\n(products/support/\nfinance)")
ks = d.box(1180, 240, 130, 48, "knowledge\nsources x3")
kb = d.box(1090, 360, 190, 48, "knowledge base\n(agentic retrieval)")
mcpend = d.box(870, 360, 170, 48, "MCP endpoint\n/knowledgebases/.../mcp")

foundry = d.cluster(750, 460, 1340, 620, "Foundry: aif-mafportsw2", kind="sub",
                    sublabel="shared infra (AIServices S0)")
model = d.node(900, 545, icon("model"), "Model deployment\ngpt-5.4-mini", note="planning + answers")
project = d.node(1230, 545, icon("project"), "Project: maf-ports")
appi = d.node(950, 670, icon("appinsights"), "App Insights\nappi-mafportsw2")
logw = d.node(1200, 670, icon("loganalytics"), "Log Analytics\nlog-mafportsw2")
d.edge(appi, logw)

d.edge(cli, agent, label="question", label_dy=-12)
d.edge(agent, mcp, label="KB first", label_t=0.5, label_dx=36)
d.edge(agent, web, label="fallback if KB misses", label_t=0.6, label_dx=-14)
d.edge(web.port("bottom", 0.3), ddg, label="HTTPS", label_t=0.5, label_dx=-28)
d.edge(mcp, mcpend, label="MCP tools/call\napi-key header", label_color=BLUE, label_t=0.5, label_dy=-24)
d.edge(mcpend, kb)
d.edge(kb, ks, label="parallel subqueries\n+ L2 semantic rerank", label_t=0.6, label_dx=52, label_dy=-16)
d.edge(ks, idx)
d.edge(kb, model, label="LLM query planning, effort=low\n(api-version 2026-05-01-preview) / api-key",
       label_color=BLUE, label_t=0.8, label_dx=130, label_dy=12)
d.edge(agent.port("bottom", 0.9), model, via=[(660, 480)],
       label="answer synthesis stays agent-side\nchat / api-key", label_color=BLUE, label_t=0.75, label_dy=-8)
d.edge(setup, srch.port("left", 0.8), label="REST: create idx x3\n+ KS x3 + KB", label_t=0.4, label_dy=-26)
d.edge(local.port("right", 0.95), appi, style="dashed", color=TELEM, via=[(730, 620)],
       label="OTel traces", label_t=0.4, label_dx=-8)

d.footer(
    notes=[
        "2-stage deploy: main.bicep (AI Search Basic only) -> scripts/setup_kb.py (indexes/KS/KB are data plane). "
        "No vectors: text + L2 rerank only, so no embedding deployment at all.",
        "$AI Search Basic is hourly (~$0.10/h = ~$75/month): delete the RG after validation (setup_kb.py rebuilds "
        "in minutes). Extra meters: retrieval tokens (Search) + query-planning tokens (your deployment).",
        "Maturity: agentic retrieval GA (2026-04-01) covers only minimal extractive search — LLM source selection "
        "/ reasoning effort / answer synthesis need the 2026-05-01-preview api-version.",
    ],
    auth=[
        "Auth: KB MCP endpoint = api-key header (dev; prod = Bearer + Search Index Data Reader) / model + "
        "planning = api-key / DuckDuckGo = keyless",
    ],
)

d.save(str(_here.parent / "architecture.png"))

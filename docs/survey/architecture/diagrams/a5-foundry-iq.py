"""A5: Foundry IQ / agentic retrieval(04章)。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/a5-foundry-iq.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import BLUE, ORANGE, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "A5: Multi-source, high-accuracy retrieval — Foundry IQ (agentic retrieval)",
    width=1400,
    height=840,
    subtitle="Knowledge base = the shared knowledge layer. MCP-served, so Agent Service, MAF, "
    "LangGraph and your own apps all consume the SAME knowledge.",
)

azc = d.cluster(60, 110, 1340, 700, "Azure subscription", kind="azure")

sc = d.cluster(560, 160, 1310, 590, "Azure AI Search (required)", kind="sub",
               sublabel="agentic retrieval engine")
kb = d.node(720, 280, icon("search"), "Knowledge base",
            note="plan -> parallel retrieve -> rerank -> synthesize")
model = d.node(1120, 280, icon("model"), "Azure OpenAI deployment\nplan + answer synthesis",
               note="query planning tokens billed to you", note_color=ORANGE)
ks1 = d.box(700, 490, 160, 44, "searchIndex\n(GA)")
ks2 = d.box(880, 490, 160, 44, "azureBlob /\nOneLake (GA)")
ks3 = d.box(1060, 490, 150, 44, "web / Bing\n(GA)")
ks4 = d.box(1230, 490, 140, 52, "SharePoint /\nSQL / MCP\n(preview)")

agent = d.node(230, 240, icon("project"), "Foundry agent\n(Agent Service)",
               note="knowledge_base_retrieve tool")
maf = d.node(230, 420, icon("cli"), "MAF / LangGraph /\nyour own app", note="same KB via MCP")
resp = d.box(230, 590, 250, 48, "Azure OpenAI Responses API\n(for per-user SharePoint authz)")

d.edge(agent, kb, label="MCP\n(2026-05-01-preview)", label_t=0.45, label_dy=-26)
d.edge(maf, kb, label="MCP", label_t=0.5, label_dy=-14)
d.edge(resp, kb, label="official path for per-user\npermission passthrough", label_color=BLUE,
       label_t=0.4, label_dy=26)
d.edge(kb, model)
d.edge(kb, ks1)
d.edge(kb, ks2)
d.edge(kb, ks3)
d.edge(kb, ks4)

d.footer(
    notes=[
        "GA vs preview is cut by REST API version: portal-built configs are ALL preview; "
        "GA requires REST/SDK 2026-04-01 directly. SLA clauses hinge on this.",
        "GA loses ingestionPermissionOptions -> 'GA config + doc-level ACL' do NOT coexist today "
        "(ACL needs 2026-05-01-preview).",
        "$Billing: AI Search knowledgeRetrieval tokens (50M free/month) + AOAI planning/synthesis. "
        "S3 HD tier has ZERO knowledge sources = agentic retrieval unusable.",
    ],
    auth=[
        "Auth: Agent Service cannot send request-scoped MCP headers -> per-user SharePoint authz "
        "officially requires the Responses API path, not Agent Service",
    ],
    config_note="Source: docs/survey/architecture/04 A5",
)

d.save(str(_here.parent.parent / "images" / "a5-foundry-iq.png"))

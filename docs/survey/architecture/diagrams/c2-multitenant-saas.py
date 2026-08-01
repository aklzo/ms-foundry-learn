"""C2: マルチテナント SaaS(06章)。C1/C3 は本図の部分集合(単一テナント / APIM 按分)のため個別図は作らない。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/c2-multitenant-saas.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import BLUE, ORANGE, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "C2: Multi-tenant SaaS — shared by default, dedicated by justification",
    width=1400,
    height=920,
    subtitle="Official default: shared model deployment. Dedicated per-tenant deployments only for "
    "quota/chargeback, filter policies, model lifecycle, fine-tuning, or residency.",
)

t = d.cluster(40, 130, 260, 440, "Tenants", kind="external")
ta = d.node(150, 220, res("onprem/client/user.png"), "Tenant A users")
tb = d.node(150, 350, res("onprem/client/user.png"), "Tenant B users")

azc = d.cluster(320, 110, 1360, 780, "Azure subscription (SaaS provider)", kind="azure")

apim = d.node(450, 270, az("integration/api-management.png"), "APIM AI gateway",
              note="llm-emit-token-metric = per-tenant chargeback", note_color=ORANGE)
api = d.box(450, 480, 250, 60, "API layer = gatekeeper\n(ALL tenant-data access\ngoes through here)")

fc = d.cluster(640, 160, 1330, 420, "Foundry", kind="sub")
shared = d.node(780, 270, icon("model"), "Shared model deployment\n(official default)",
                note="app must enforce tenant/deployment rules")
dedic = d.node(1040, 270, icon("model"), "Dedicated deployment\n(large tenants)",
               note="TPM quota / filters / FT / residency")
proj = d.node(1240, 270, icon("project"), "Project")

data = d.cluster(640, 460, 1330, 750, "Tenant data (store-per-tenant or shared+filter)", kind="sub")
search = d.node(780, 570, icon("search"), "AI Search\nindex per tenant",
                note="B2C-scale -> shared store + filter")
cosmos = d.node(1020, 570, az("databases/azure-cosmos-db.png"), "Cosmos DB\npartition per tenant")
blob = d.node(1230, 570, az("storage/storage-accounts.png"), "Blob\nper tenant")

d.edge(ta, apim, label="tenant ID", label_t=0.5, label_dy=-14)
d.edge(tb, apim)
d.edge(apim, api)
d.edge(apim, fc.port("left", 0.4), label="rate limit / token\nmetering per tenant",
       label_color=ORANGE, label_t=0.5, label_dy=-28)
d.edge(api, data.port("left", 0.4), label="tenant-scoped queries +\naudit log of grounding data",
       label_t=0.65, label_dy=30)

d.footer(
    notes=[
        "Official pitfalls: shared instances give NO per-deployment security isolation; noisy "
        "neighbor; NEVER share an instance that hosts fine-tuned models.",
        "Responses API weakens tenant isolation (official): scope response IDs to tenants in "
        "YOUR store; built-in tools (Code Interpreter / MCP) need per-tenant containers/configs.",
        "$Chargeback is app-side by design: track per-tenant tokens in the app (APIM metric "
        "eases this). Limits: 32 deployments/resource, 100 Foundry resources/region/sub.",
    ],
    auth=[
        "Auth: never let LLM output carry tenant identity (official: don't rely on the model to "
        "propagate tenant info); per-user conversation authz stays app responsibility",
    ],
    config_note="Source: docs/survey/architecture/06 C2 (C1 = single-tenant subset / C3 = APIM capacity view)",
)

d.save(str(_here.parent.parent / "images" / "c2-multitenant-saas.png"))

"""D1: 規制業種・閉域 BYO VNet(07章)のアーキテクチャ図。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/d1-closed-network.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import BLUE, ORANGE, TELEM, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "D1: Regulated industry / closed network — BYO VNet (standard agent setup)",
    width=1400,
    height=960,
    subtitle="Design starts from the list of features that do NOT work in a closed network. "
    "This gate cannot be retrofitted (setup is immutable after creation).",
)

# --- corp network ------------------------------------------------------------
corp = d.cluster(40, 130, 290, 400, "Corporate network", kind="external")
user = d.node(160, 230, res("onprem/client/user.png"), "User",
              note="ExpressRoute / VPN - no internet path")
dns = d.box(160, 340, 200, 40, "on-prem DNS ->\n168.63.129.16 fwd")

# --- Azure -------------------------------------------------------------------
azc = d.cluster(340, 110, 1360, 780, "Azure subscription (same region as VNet)", kind="azure")
vnet = d.cluster(370, 160, 1330, 750, "VNet (RFC1918)", kind="sub",
                 sublabel="Private DNS zones x6 (privatelink.*)")

pe = d.node(470, 270, az("network/private-endpoint.png"),
            "Private Endpoint\n(Foundry account)", note="approved state only")

fc = d.cluster(590, 200, 1300, 360, "Foundry (standard agent setup)", kind="sub")
foundry = d.node(700, 280, icon("foundry"), "Foundry\naccount")
project = d.node(900, 280, icon("project"), "Project", note="capability host: immutable")
model = d.node(1120, 280, icon("model"), "Model deployment\n(Regional Standard)",
               note="Japan East for JP data residency")

sub = d.cluster(590, 390, 1010, 560, "Delegated subnet", kind="sub",
                sublabel="Microsoft.App/env, /24 in prod")
micro = d.node(680, 480, icon("containerapp"), "Micro VM\n(hosted agent session)")
tools = d.box(830, 460, 130, 40, "Tools Service")
proxy = d.box(830, 520, 150, 40, "Data Proxy\n(single-tenant)")

data = d.cluster(1040, 390, 1310, 720, "BYO data (all PE)", kind="sub")
cosmos = d.node(1115, 470, az("databases/azure-cosmos-db.png"),
                "Cosmos DB", note="3,000+ RU/s required")
storage = d.node(1250, 470, az("storage/storage-accounts.png"), "Storage")
search = d.node(1180, 625, az("appservices/cognitive-search.png"),
                "AI Search\n(own index = the RAG)")

fw = d.node(470, 600, az("network/firewall.png"), "Azure Firewall",
            note="FQDN allowlist / NO TLS inspection", note_color=ORANGE)

# --- egress ------------------------------------------------------------------
out = d.cluster(40, 540, 290, 720, "Microsoft endpoints", kind="external")
ms = d.node(160, 620, icon("entra"), "Entra ID / Monitor",
            note="service tags: AzureActiveDirectory etc.")

# --- edges -------------------------------------------------------------------
d.edge(user, pe, label="private traffic only", label_t=0.5, label_dy=-14)
d.edge(pe, foundry)
d.edge(foundry, micro, route="vh", label="session start", label_t=0.6, label_dx=-52)
d.edge(micro, tools)
d.edge(tools, proxy)
d.edge(proxy, data.port("left", 0.3), label="PE per resource\n(not auto-created)", label_t=0.5,
       label_dy=-26)
d.edge(sub.port("left", 0.7), fw, label="controlled egress", label_t=0.5, label_dy=18, label_dx=-10)
d.edge(fw, ms, label="allowlisted FQDN\n/ service tags", label_t=0.5, label_dy=-24)

d.footer(
    notes=[
        "NOT available in closed network: File Search / Memory / Work IQ / Logic Apps tool / "
        "Browser Automation / Computer Use / Image Generation.",
        "Tracing VNet support is inconsistent across official pages -> assume unsupported. "
        "Consequence: RAG / memory / observability all self-built ('closed + full managed' does not exist).",
        "capability host cannot be updated after creation -> config change = delete & recreate "
        "(agents lose conversations/files). IaC must assume rebuild.",
    ],
    auth=[
        "Auth: Entra ID only end-to-end. TLS inspection on the egress firewall BREAKS agent connections "
        "- conflicts with common JP-FSI SSL-visibility policy: get the exception approved early.",
    ],
    config_note="Source: docs/survey/architecture/07 (BYO VNet / standard agent setup)",
)

d.save(str(_here.parent.parent / "images" / "d1-closed-network.png"))

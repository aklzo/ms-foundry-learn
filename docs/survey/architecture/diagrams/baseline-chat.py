"""公式-B: Baseline Microsoft Foundry Chat(01章)のアーキテクチャ図。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/baseline-chat.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import BLUE, ORANGE, TELEM, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "Official-B: Baseline Microsoft Foundry Chat (AAC reference architecture)",
    width=1400,
    height=1010,
    subtitle="Network-isolated, single-region, zone-redundant. Named by WAF as the recommended "
    "architecture for AI workloads. Production starting point.",
)

# --- internet (ingress) ------------------------------------------------------
inet = d.cluster(40, 110, 230, 300, "Internet", kind="external")
user = d.node(135, 190, res("onprem/client/user.png"), "User\n(browser)")

# --- Azure -------------------------------------------------------------------
azc = d.cluster(280, 110, 1360, 830, "Azure subscription (single region, zone redundant)", kind="azure")
vnet = d.cluster(310, 160, 1330, 800, "VNet", kind="sub",
                 sublabel="all subnets NSG-controlled, UDR to Azure Firewall")

ddos = d.node(420, 260, az("network/ddos-protection-plans.png"), "DDoS Protection\n+ public IP")
appgw = d.node(610, 260, az("network/application-gateway.png"),
               "Application Gateway\n+ WAF", note="snet-appGateway / TLS termination")
appsvc = d.node(830, 260, az("appservices/app-services.png"),
                "App Service (chat UI)\n3 zones", note="managed identity")

foundry_c = d.cluster(950, 350, 1310, 550, "Foundry account (standard agent setup)", kind="sub")
foundry = d.node(1040, 450, icon("foundry"), "Foundry\nAgent Service")
project = d.node(1220, 450, icon("project"), "Project", note="capability host")

pe_c = d.cluster(660, 580, 1310, 770, "snet-privateEndpoints", kind="sub")
cosmos = d.node(760, 660, az("databases/azure-cosmos-db.png"),
                "Cosmos DB\nconversations", note="PITR backup")
storage = d.node(960, 660, az("storage/storage-accounts.png"), "Storage\nuploaded files")
search = d.node(1180, 660, az("appservices/cognitive-search.png"),
                "AI Search\nFile Search index", note="keep source of truth elsewhere")

egress_box = d.box(480, 460, 300, 44, "snet-agentsEgress\n(delegated Microsoft.App/environments, /24)")
fw = d.node(480, 590, az("network/firewall.png"), "Azure Firewall",
            note="allowed public FQDN only / NO TLS inspection", note_color=ORANGE)
bastion = d.node(370, 720, az("networking/bastions.png"), "Bastion")
jump = d.box(530, 730, 190, 44, "jump box VM /\nbuild agent VM")

# --- internet (egress) -------------------------------------------------------
out = d.cluster(40, 490, 230, 690, "Internet (egress)", kind="external")
ext = d.node(135, 570, icon("browser"), "External tools\n(MCP / APIs)")

# --- edges -------------------------------------------------------------------
d.edge(user, ddos, label="HTTPS 443")
d.edge(ddos, appgw)
d.edge(appgw, appsvc)
d.edge(appsvc, foundry, label="Private Endpoint", label_t=0.7, label_dy=-10)
d.edge(project, cosmos)
d.edge(project, storage)
d.edge(project, search)
d.edge(foundry_c.port("left", 0.5), egress_box, label="external tool calls", label_t=0.5, label_dy=-14)
d.edge(egress_box, fw)
d.edge(fw, ext, label="allowed FQDN only", label_t=0.5, label_dy=-14)
d.edge(bastion, jump)
d.edge(jump, foundry_c.port("bottom", 0.25), style="dashed", color=TELEM,
       label="ops access", label_t=0.5, label_dy=-12)

d.footer(
    notes=[
        "Web search tool calls api.bing.microsoft.com internally and BYPASSES the egress subnet "
        "-> validate every tool against egress policy (stated in the article).",
        "No built-in DR: no state replication / backup / PITR in Agent Service -> recovery = rebuild "
        "(mitigate: Cosmos PITR, agent-as-code, user-assigned MI, delete locks).",
        "$Top costs: Cosmos DB / AI Search / DDoS Protection, then UI compute + App Gateway. "
        "Agents call tools non-deterministically -> external API cost can spike.",
    ],
    auth=[
        "Auth: user -> Entra ID / App Service & prompt agents -> shared project managed identity "
        "(split projects per access pattern) / per-user conversation authz = app responsibility (BOLA)",
    ],
    config_note="Source: AAC baseline-microsoft-foundry-chat -> docs/survey/architecture/01",
)

d.save(str(_here.parent.parent / "images" / "baseline-chat.png"))

"""A2: 全社ナレッジ検索(AI Search 自前索引・04章)のアーキテクチャ図。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/a2-knowledge-search.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import BLUE, ORANGE, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "A2: Company-wide knowledge search — own AI Search index (production standard)",
    width=1400,
    height=990,
    subtitle="Per-user document visibility (security filter / ACL). You own chunking, embeddings, "
    "metadata; integrated vectorization + semantic ranker stay managed.",
)

# --- sources -----------------------------------------------------------------
src = d.cluster(40, 130, 300, 420, "Document sources", kind="external")
docs = d.node(170, 220, icon("files"), "Blob / SharePoint /\nfile server", note="10k-100k+ documents")

# --- Azure -------------------------------------------------------------------
azc = d.cluster(350, 110, 1360, 700, "Azure subscription", kind="azure")

ing = d.cluster(380, 160, 900, 480, "Ingestion pipeline (you own the design)", kind="sub")
di = d.node(480, 260, az("aimachinelearning/cognitive-services.png"),
            "Document Intelligence /\nContent Understanding", note="structure extraction (tables, headings)")
idx = d.box(700, 260, 190, 60, "AI Search indexer\n+ skillset\n(Text Split + embed)")
search = d.node(640, 410, az("appservices/cognitive-search.png"),
                "AI Search index\nACL / metadata / semantic", note="chunk 512 tok / overlap 25% (official)")

fc = d.cluster(950, 160, 1330, 400, "Foundry", kind="sub")
agent = d.node(1050, 260, icon("project"), "Project\nPrompt or Hosted agent",
               note="AI Search tool (top_k / filter)")
model = d.node(1240, 260, icon("model"), "Model\ndeployment")

appsvc = d.node(1100, 545, az("appservices/app-services.png"),
                "App Service\nresolves user identity",
                note="filter or x-ms-query-source-authorization")
user = d.node(1100, 780, res("onprem/client/user.png"), "User", note="sees only permitted documents")

# --- edges -------------------------------------------------------------------
d.edge(docs, di, label="ingest", label_t=0.5, label_dy=-14)
d.edge(di, idx)
d.edge(idx, search, label="integrated vectorization\n(index projections)", label_t=0.65, label_dx=28, label_dy=16)
d.edge(agent, model)
d.edge(agent, search, label="hybrid + semantic query\nPrivate Endpoint", label_color=BLUE,
       label_t=0.28, label_dy=-30)
d.edge(user, appsvc, label="Entra ID sign-in", label_color=BLUE, label_t=0.5, label_dx=76)
d.edge(appsvc, agent, label="user groups ->\nsecurity filter", label_t=0.45, label_dx=66)

d.footer(
    notes=[
        "Chunk strategy is a semi-permanent choice (official wording) - re-chunking means full re-index. "
        "Decide chunk size / overlap / language analyzer up front.",
        "$Semantic ranker reranks TOP-50 only (L1 recall failures cannot be rescued); vector index quota "
        "per partition is a hard limit (Basic 5GB / S1 35GB / S2 150GB / S3 300GB).",
        "Doc-level ACL: security filter (GA, group IDs in index) or query-source-authorization "
        "(preview) - see ch.04 for the 4 options.",
    ],
    auth=[
        "Auth: user -> Entra ID / agent -> AI Search via managed identity + PE / "
        "per-user visibility enforced in the query, never in the prompt",
    ],
    config_note="Source: docs/survey/architecture/04 A2 (closed-network variant: ch.07)",
)

d.save(str(_here.parent.parent / "images" / "a2-knowledge-search.png"))

"""Architecture diagram for corrective-rag (Port 4).

Regenerate:  uv run --with diagrams,pillow python ports/corrective-rag/docs/architecture.py
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
    "corrective-rag — CRAG loop + Azure AI Search (Port 4)",
    width=1400,
    height=820,
    subtitle="retrieve -> per-doc grading -> (single, non-looping) corrective pass; Qdrant replaced by "
    "AI Search Free, client-side embeddings",
)

local = d.cluster(40, 100, 720, 520, "Local machine (uv + MAF)", kind="local")
wf = d.cluster(170, 150, 700, 430, "MAF workflow (switch-case)", kind="sub")
ext = d.cluster(40, 545, 360, 690, "External web (outside Azure)", kind="external")

cli = d.node(100, 280, icon("cli"), "CLI\ncorrective-rag-maf")
retrieve = d.box(260, 215, 130, 48, "retrieve\n(vector top-4)")
grade = d.box(440, 215, 150, 48, "grade\n(per-doc yes/no)")
transform = d.box(285, 350, 150, 48, "transform_query\n(rewrite)")
websearch = d.box(465, 350, 140, 48, "web_search\n(DDG, 3 tries)")
generate = d.box(625, 283, 100, 48, "generate")
setup = d.box(555, 472, 230, 40, "scripts/setup_index.py (one-time)")
ddg = d.node(180, 600, icon("browser"), "DuckDuckGo HTML", note="keyless HTTPS")

azure = d.cluster(760, 100, 1360, 695, "Azure subscription — rg-maf-ports (Japan East)", kind="azure")
foundry = d.cluster(790, 150, 1330, 470, "Foundry: aif-mafports", kind="sub",
                    sublabel="shared infra (AIServices S0)")
model = d.node(930, 235, icon("model"), "Model deployment\ngpt-5.4-mini", note="shared (grade/rewrite/generate)")
project = d.node(1215, 235, icon("project"), "Project: maf-ports", note="system MI")
embed = d.node(930, 375, icon("model"), "Embedding deployment\ntext-embedding-3-small",
               note="added by this port (main.bicep)")
search = d.node(880, 590, icon("search"), "AI Search: srch-mafports\nFree SKU", note="3 indexes / 50 MB",
                note_color=ORANGE)
appi = d.node(1100, 590, icon("appinsights"), "App Insights\nappi-mafports")
logw = d.node(1290, 590, icon("loganalytics"), "Log Analytics\nlog-mafports")
d.edge(appi, logw)

d.edge(cli, retrieve, label="question", label_dy=-12)
d.edge(retrieve, grade)
d.edge(grade, generate, label="Default:\nall relevant", label_t=0.5, label_dy=-24)
d.edge(grade, transform, label="Case: low\nrelevance", label_t=0.5, label_dx=-52)
d.edge(transform, websearch)
d.edge(websearch, generate, label="1 pass, no re-grade", label_t=0.75, label_dy=34)
d.edge(websearch.port("bottom", 0.2), ddg, label="search_with_retry\n(4s/8s backoff)", label_t=0.5, label_dx=-8)

d.edge(wf.port("right", 0.2), model, label="chat: grade x docs +\nrewrite + generate / api-key",
       label_color=BLUE, label_t=0.35, label_dy=-26)
d.edge(wf.port("right", 0.55), embed, label="query embedding (1536-d)\napi-key", label_color=BLUE,
       label_t=0.45, label_dy=16)
d.edge(wf.port("right", 0.85), search, label="vector query (HNSW, k=4)\nadmin api-key", label_color=BLUE,
       label_t=0.28, label_dy=-28)
d.edge(setup, search, label="create index +\nupsert 11 chunks", label_t=0.45, label_dy=24)
d.edge(local.port("right", 0.93), appi, style="dashed", color=TELEM,
       label="OTel traces (executor +\nper-doc grader spans)", label_t=0.45, label_dy=-24)

d.footer(
    notes=[
        "2-stage deploy: infra/main.bicep (AI Search Free + embedding deployment) -> scripts/setup_index.py "
        "(index schema + documents = data plane, not expressible in ARM/Bicep).",
        "$AI Search Free tier: $0/month but 3 indexes / 50 MB / no semantic ranker / no SLA / 1 free service "
        "per subscription. Chat + embedding tokens billed per call.",
    ],
    auth=[
        "Auth: chat + embeddings = api-key (lab .env) / AI Search = admin api-key (lab; prod -> RBAC + Key Vault) / "
        "DuckDuckGo = none (keyless)",
    ],
)

d.save(str(_here.parent / "architecture.png"))

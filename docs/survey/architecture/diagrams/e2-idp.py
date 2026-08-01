"""E2: 文書処理・IDP パイプライン(08章)。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/e2-idp.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import BLUE, ORANGE, TELEM, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "E2: Document processing / IDP — queue-driven pipeline with human review",
    width=1400,
    height=880,
    subtitle="Pick DI vs Content Understanding FIRST: fixed forms = DI prebuilt / multimodal & "
    "RAG prep = CU / air-gapped = DI container (CU has none).",
)

src = d.cluster(40, 130, 250, 400, "Document intake", kind="external")
docs = d.node(140, 240, icon("files"), "Blob / SharePoint /\nmail / scanner")

azc = d.cluster(300, 110, 1360, 720, "Azure subscription", kind="azure")
queue = d.node(430, 260, az("integration/service-bus.png"), "Service Bus /\nQueue Storage",
               note="backpressure + retry")
worker = d.node(650, 260, icon("containerapp"), "Worker",
                note="Durable Functions / CA jobs / indexer")
di = d.node(890, 260, az("aimachinelearning/cognitive-services.png"),
            "DI Layout /\nContent Understanding", note="CU: BYO LLM + embedding deployments")
chunk = d.box(890, 440, 240, 48, "chunk + embed\n(SK TextChunker)")
search = d.node(1130, 440, icon("search"), "AI Search\nindex")
cosmos = d.node(1280, 590, az("databases/azure-cosmos-db.png"), "Cosmos DB\n(metadata)")
review = d.box(650, 460, 220, 48, "confidence < threshold\n-> human review")
agent = d.node(1130, 620, icon("project"), "Foundry agent",
               note="search & QA over results")

d.edge(docs, queue)
d.edge(queue, worker)
d.edge(worker, di, label="analyze", label_t=0.5, label_dy=-14)
d.edge(di, chunk, label="$ embeddings via Batch\ndeploy = 50% off", label_color=ORANGE,
       label_t=0.5, label_dx=95)
d.edge(chunk, search)
d.edge(chunk, cosmos, via=[(890, 555), (1240, 555)])
d.edge(worker, review, style="dashed", color=TELEM, label="low confidence", label_t=0.5,
       label_dx=-60)
d.edge(agent, search, label="query", label_t=0.5, label_dx=40)

d.footer(
    notes=[
        "Page limits flip: CU max 300 pages vs DI Layout 2,000 -> split long PDFs upstream or "
        "choose DI. DOCX/HTML billed at 3,000 chars = 1 page (DI).",
        "Both AI Search skills: layout processing > 5 min TIMES OUT and is still billed. "
        "DI v4 markdown outputs tables as HTML (not pipes) - write parsers accordingly.",
        "CU GA breaking changes: Pro mode & Face API dropped; managed model capacity removed "
        "(bring your own deployments; exceptions: prebuilt-read / prebuilt-layout only).",
    ],
    auth=[
        "Auth: worker -> DI/CU via managed identity / review UI scoped to reviewer role",
    ],
    config_note="Source: docs/survey/architecture/08 E2 (air-gapped variant: 07 §9.3)",
)

d.save(str(_here.parent.parent / "images" / "e2-idp.png"))

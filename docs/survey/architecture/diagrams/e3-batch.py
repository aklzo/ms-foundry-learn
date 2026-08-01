"""E3: 大量バッチ処理(08章)。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/e3-batch.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import BLUE, ORANGE, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "E3: Bulk batch processing — carve out everything that isn't real-time",
    width=1400,
    height=680,
    subtitle="Moving non-interactive work to Batch halves model cost. Quota pools are separate, "
    "so daytime chat and nightly bulk jobs coexist safely on one resource.",
)

src = d.node(140, 260, az("storage/blob-storage.png"), "Input data\n(Blob / DB / events)")
gen = d.box(370, 260, 220, 52, "JSONL job builder\n(Functions / CA jobs)")

azc = d.cluster(640, 110, 1340, 520, "Azure subscription", kind="azure")
batch = d.node(790, 260, icon("model"), "Batch deployment",
               note="50% off Global Standard / 24h window (fixed)", note_color=ORANGE)
res_blob = d.node(1030, 260, az("storage/blob-storage.png"), "Result JSONL",
                  note="BYO Blob up to 1GB input")
post = d.box(1230, 260, 170, 52, "post-process /\ningest results")

d.edge(src, gen)
d.edge(gen, batch, label="submit; on token_limit_exceeded:\nfail-fast + exp backoff",
       label_t=0.45, label_dy=-30)
d.edge(batch, res_blob, label="<= 24h target", label_t=0.5, label_dy=-14)
d.edge(res_blob, post)

d.footer(
    notes=[
        "$Enqueued-token quota is fully separated from online TPM -> a runaway batch cannot "
        "starve the real-time path. Turn Dynamic quota ON for opportunistic capacity.",
        "Limits: 100,000 requests / file; completion_window accepts ONLY '24h' (anything else "
        "fails the job); jobs continue past 24h rather than expiring.",
        "Other cost levers stack: Model router Cost mode, small models (gpt-4.1-nano ~20x PTU "
        "efficiency), prompt caching (identical 1,024-token prefix).",
    ],
    config_note="Source: docs/survey/architecture/08 E3",
)

d.save(str(_here.parent.parent / "images" / "e3-batch.png"))

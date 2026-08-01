"""E6: ファインチューニング運用(08章)。処理フロー(MLOps ループ)として描く。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/e6-finetune-ops.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import BLUE, ORANGE, TELEM, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "E6: Fine-tuning operations — it is a loop, not a one-shot",
    width=1400,
    height=860,
    subtitle="Most cases don't need FT (ground with RAG first). When they do: SFT -> DPO, "
    "serverless training, Developer tier for evals, and plan for base-model retirement.",
)

data = d.node(140, 280, az("storage/storage-accounts.png"), "Training data",
              note="500+ prompt/response pairs for prod")

azc = d.cluster(290, 110, 1360, 700, "Azure subscription", kind="azure")
ft = d.node(440, 280, az("aimachinelearning/azure-applied-ai-services.png"),
            "Fine-tuning job\n(SFT -> DPO stack)", note="serverless = best balance (official)")
reg = d.box(660, 280, 200, 48, "custom model\n(storage itself is free)")
dev = d.node(920, 200, icon("model"), "Developer tier deploy",
             note="no hourly fee / no SLA / auto-delete 24h", note_color=ORANGE)
ev = d.node(1160, 200, icon("evals"), "Evaluations")
prod = d.node(920, 460, icon("model"), "Production deploy\n(Standard / PTU)",
              note="hourly fee even if idle; deleted after 15 idle days", note_color=ORANGE)
mon = d.node(1160, 460, icon("appinsights"), "Monitoring\n+ keepalive")
retire = d.box(660, 610, 320, 52, "base model retirement -> re-finetune\n(training stops ~6 months before inference)")

d.edge(data, ft)
d.edge(ft, reg)
d.edge(reg, dev, route="hv", label="evaluate first", label_t=0.35, label_dy=16)
d.edge(dev, ev)
d.edge(ev, prod, label="quality gate passed", label_t=0.75, label_dy=-20, via=[(1040, 330)])
d.edge(reg, prod, route="hv")
d.edge(prod, mon)
d.edge(mon, retire, style="dashed", color=TELEM, label="retirement notice", label_t=0.5,
       label_dy=22, route="vh")
d.edge(retire, ft, route="hv", label="repeat with new base", label_t=0.6, label_dy=18)

d.footer(
    notes=[
        "$Two rules bite together: every deployed FT model bills hourly EVEN UNUSED, and a "
        "deployment idle > 15 days is silently deleted -> keepalive or redeploy runbook.",
        "2-stage retirement: training retires first (~2027-04 for current bases), deployment "
        "~6 months later -> FT is never 'build once'; budget periodic re-tuning.",
        "Global Standard deploys may store custom weights OUTSIDE the geography (preview) - "
        "regulated deals need Standard (regional). Cross-region deploy = SDK/REST only.",
    ],
    config_note="Source: docs/survey/architecture/08 E6",
)

d.save(str(_here.parent.parent / "images" / "e6-finetune-ops.png"))

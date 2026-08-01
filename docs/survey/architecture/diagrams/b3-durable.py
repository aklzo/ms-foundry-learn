"""B3: 長時間・確実な再開(MAF + Durable Extension + DTS、05章)。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/b3-durable.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import BLUE, ORANGE, TELEM, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "B3: Long-running processes with guaranteed resume — MAF + Durable Extension",
    width=1400,
    height=800,
    subtitle="Multi-day approvals, waiting on external batches, resume-from-failed-step. "
    "Check this BEFORE concluding 'MAF can't do long-running, switch to LangGraph'.",
)

user = d.node(130, 250, res("onprem/client/user.png"), "User / approver",
              note="approval can take days")
evt = d.box(130, 420, 190, 44, "external system\nevent / batch done")

azc = d.cluster(300, 110, 1340, 650, "Azure subscription", kind="azure")
host = d.cluster(330, 160, 860, 600, "Azure Functions host (or bring-your-own-compute)",
                 kind="sub", sublabel="scale-to-zero / MCP server trigger")
maf = d.box(480, 270, 230, 64, "MAF agent / workflow\n(core logic UNCHANGED\nby the extension)")
dur = d.box(480, 430, 230, 48, "Durable Extension\n(auto checkpoints)")
hitl = d.box(740, 350, 170, 48, "HITL wait\n(hours - days)")

dts = d.node(1030, 290, icon("scheduler"), "Durable Task\nScheduler (DTS)",
             note="dashboard + local emulator (CI-friendly)")
store = d.node(1030, 490, az("storage/storage-accounts.png"), "Durable state\n(full thread history)",
               note="per thread ID, survives restarts")

d.edge(user, maf, label="request", label_t=0.5, label_dy=-14)
d.edge(evt, host.port("left", 0.75), label="resume signal", label_t=0.5, label_dy=16)
d.edge(maf, hitl, label="request info", label_t=0.5, label_dy=-14)
d.edge(hitl, user, label="approve / reject", label_color=BLUE, label_t=0.35, label_dy=18)
d.edge(maf, dur)
d.edge(dur, dts, label="checkpoint per\nsuperstep", label_t=0.82, label_dx=10, label_dy=0,
       via=[(1030, 430)])
d.edge(dts, store)
d.edge(dts, maf, style="dashed", color=TELEM, label="recover / resume\nafter fault or deploy",
       label_t=0.45, label_dy=-26)

d.footer(
    notes=[
        "Backend: DTS recommended (highest perf, managed, built-in observability dashboard). "
        "Reliable streaming across distributed hosts needs a separate Redis-class broker.",
        "No official pattern for DTS INSIDE a Foundry hosted agent was found -> host on Functions "
        "or your own compute when Durable is required.",
        "If AI is just one step and approvals/waits dominate, Logic Apps / Durable Functions alone "
        "may be the better main engine (-> B5).",
    ],
    auth=[
        "Auth: approver via your app (Entra ID) / Functions -> DTS via managed identity",
    ],
    config_note="Source: docs/survey/architecture/05 B3",
)

d.save(str(_here.parent.parent / "images" / "b3-durable.png"))

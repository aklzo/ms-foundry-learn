"""Architecture diagram for critique-loop (Port 9).

Regenerate:  uv run --with diagrams,pillow python ports/critique-loop/docs/architecture.py
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
    "critique-loop — self-critique loop + cloud evals (Port 9)",
    width=1400,
    height=830,
    subtitle="Runtime critic = control signal (in the request path); Foundry cloud evals = measurement "
    "(async jobs) — including the final revision the critic never sees",
)

local = d.cluster(40, 100, 720, 560, "Local machine (uv + MAF)", kind="local")
wf = d.cluster(170, 140, 700, 460, "MAF workflow (fan-out + loop edge)", kind="sub")

cli = d.node(100, 300, icon("cli"), "CLI\ncritique-loop-maf")
disp = d.box(250, 250, 120, 44, "dispatcher")
c1 = d.box(445, 190, 170, 36, "candidate: structured")
c2 = d.box(445, 250, 170, 36, "candidate: practical")
c3 = d.box(445, 310, 170, 36, "candidate: skeptical")
synth = d.box(625, 250, 120, 44, "synthesize\n(fan-in)")
critic = d.box(445, 400, 150, 48, "critic\n(verdict + critiques)")
revise = d.box(250, 400, 110, 44, "revise")
final = d.box(630, 400, 110, 44, "finalize")
evalbox = d.box(380, 510, 380, 40, "scripts/run_cloud_eval.py (per saved run, offline judge)")

azure = d.cluster(760, 100, 1360, 700, "Azure subscription — rg-maf-ports (Japan East)", kind="azure")
foundry = d.cluster(790, 150, 1330, 480, "Foundry: aif-mafportsw2", kind="sub",
                    sublabel="shared infra (AIServices S0)")
model = d.node(930, 240, icon("model"), "Model deployment\ngpt-5.4-mini", note="loop roles + eval judge")
project = d.node(1215, 240, icon("project"), "Project: maf-ports")
evals = d.node(1075, 390, icon("evals"), "Cloud evals (data plane)\nevals.create -> runs",
               note="builtin.coherence / fluency + score_model")
appi = d.node(950, 610, icon("appinsights"), "App Insights\nappi-mafportsw2")
logw = d.node(1200, 610, icon("loganalytics"), "Log Analytics\nlog-mafportsw2")
d.edge(appi, logw)

d.edge(cli, disp, label="prompt", label_dy=-12)
for c in (c1, c2, c3):
    d.edge(disp, c)
    d.edge(c, synth)
d.edge(synth, critic, label="draft", label_t=0.55, label_dx=30)
d.edge(critic, revise, label="Case: revise\n(critique list)", label_t=0.5, label_dy=-26)
d.edge(revise.port("top", 0.5), synth.port("bottom", 0.3), via=[(250, 345), (601, 345)],
       label="loop: revised draft (rounds <= max, default 2)", label_t=0.5, label_dy=14)
d.edge(critic, final, label="accept or\nmax rounds", label_t=0.5, label_dy=-26)

d.edge(wf.port("right", 0.3), model, label="chat: 3 candidates + synth\n+ critic + revise / api-key",
       label_color=BLUE, label_t=0.4, label_dy=-28)
d.edge(evalbox, evals, label="submit versions (openai .evals\nvia project) — Entra ID", label_color=BLUE,
       label_t=0.5, label_dy=26)
d.edge(evals, model, label="judge calls (deployment_name\n= gpt-5.4-mini) — token billing", label_color=ORANGE,
       label_t=0.5, label_dx=-16, label_dy=18)
d.edge(local.port("right", 0.92), appi, style="dashed", color=TELEM,
       label="OTel traces", label_t=0.4, label_dy=-14)

d.footer(
    notes=[
        "Eval groups/runs are data-plane objects (no ARM type) — Bicep stays existing-refs-only; "
        "run_cloud_eval.py drives evals.create -> runs.create -> poll -> output_items.",
        "$Judge cost lands on your own deployment (initialization_parameters.deployment_name is required for "
        "builtin evaluators): versions x 3 graders per eval run.",
        "Live finding: critic kept saying 'revise' while cloud eval showed fluency -1.0 — control signal and "
        "measurement disagree; final revision is only ever scored by the cloud eval.",
    ],
    auth=[
        "Auth: loop chat = api-key / evals submission = Entra ID (bearer via get_openai_client; submitter needs "
        "Foundry User data-plane role) / traces = App Insights conn string",
    ],
)

d.save(str(_here.parent / "architecture.png"))

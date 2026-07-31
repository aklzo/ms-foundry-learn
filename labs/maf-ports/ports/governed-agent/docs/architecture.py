"""Architecture diagram for governed-agent (Port 14).

Regenerate:  uv run --with diagrams,pillow python ports/governed-agent/docs/architecture.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
for _p in _here.parents:
    if (_p / "tools" / "archdiagram.py").exists():
        sys.path.insert(0, str(_p / "tools"))
        break
from archdiagram import BLUE, NOTE_SHARED_ONLY, ORANGE, TELEM, Diagram, icon, std_azure  # noqa: E402

d = Diagram(
    "governed-agent — MAF middleware governance (Port 14)",
    width=1400,
    height=840,
    subtitle="Expense-approval agent wrapped in app-layer governance: deterministic policy "
    "interception, trust-gated stages, SHA-256 hash-chained audit ledger",
)

local = d.cluster(40, 100, 730, 660, "Local machine (uv + MAF)", kind="local")
mw = d.cluster(210, 190, 710, 480, "Agent + middleware pipeline (onion order)", kind="sub")

cli = d.node(125, 350, icon("cli"), "CLI\ngoverned-agent-maf")
policy = d.box(300, 250, 175, 56, "PolicyEnforcement\n(function middleware)")
audit_mw = d.box(490, 250, 165, 56, "ToolAudit +\nAgentAudit")
tools = d.box(300, 380, 175, 56, "expense tools\n(submit / lookup)")
trust = d.box(490, 380, 165, 56, "trust gate\n(gold/silver/bronze)")
ledger = d.node(340, 580, icon("files"), "audit ledger (JSONL)\nhash-chained", note="--verify = independent check")
hitl = d.node(560, 580, icon("user"), "HITL queue\n(approval band)", note="stub (extension point)")

shared = std_azure(d, base="mafportsw3", rg="rg-maf-ports-w3", y1=660)

d.edge(cli, policy.port("left", 0.5), label="expense request", label_dy=-14, label_dx=-8)
d.edge(policy, audit_mw, label="pass", label_dy=-12)
d.edge(policy.port("bottom", 0.5), tools.port("top", 0.5),
       label="blocked -> context.result\n(refusal seen by model)", label_color=ORANGE,
       label_t=0.5, label_dx=-6, style="dashed")
d.edge(audit_mw.port("bottom", 0.5), trust.port("top", 0.5))
d.edge(tools.port("bottom", 0.4), ledger.port("top", 0.4), label="every call\n+ SHA-256 chain", label_t=0.55, label_dx=-56)
d.edge(trust.port("bottom", 0.5), hitl.port("top", 0.4), label="below threshold", label_t=0.5, label_dx=52)
d.edge(mw.port("right", 0.35), shared["model"], label="chat (loop iterations)\napi-key", label_color=BLUE,
       label_t=0.45, label_dy=-26)
d.edge(local.port("right", 0.9), shared["appi"], style="dashed", color=TELEM,
       label="OTel traces (blocked calls\nleave no tool span)", label_t=0.45, label_dy=-6)

d.footer(
    notes=[
        NOTE_SHARED_ONLY,
        "Governance lives in the app layer (MAF middleware): deterministic rules have no service-layer home. "
        "Foundry agent guardrails (preview) complement, not replace, this stack (survey features/06).",
        "Audit vs traces: hash chain proves integrity but holds content; traces visualize flow but cannot "
        "record blocked-before-execution calls — two orthogonal records fed from the same interception point.",
    ],
    auth=[
        "Auth: model data plane = api-key (lab .env) / traces = App Insights connection string / "
        "ledger + policies = local files (no Azure resources beyond shared).",
    ],
)

d.save(str(_here.parent / "architecture.png"))

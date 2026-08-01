"""D3: エッジ・オンプレ 3 形態(07章 §9)。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/d3-edge-onprem.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import BLUE, ORANGE, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "D3: Edge / on-prem — three DIFFERENT products that share a name",
    width=1400,
    height=860,
    subtitle="Sort these out first: per-device SDK (GA) vs on-prem K8s inference (preview, "
    "request-only) vs air-gapped tool containers (per-service).",
)

c1 = d.cluster(40, 120, 460, 740, "End-user device — Foundry Local (GA)", kind="local")
app = d.node(170, 260, icon("cli"), "Your app + SDK\n(in-process, ONNX)",
             note="~20MB, GPU/NPU auto-detect")
m1 = d.box(170, 430, 280, 52, "Chat models (GPT-OSS / Phi /\nQwen / Mistral...) + Whisper ONLY")
n1 = d.box(170, 560, 280, 52, "single user per device\nNOT a server runtime (official)")
d.edge(app, m1)

c2 = d.cluster(490, 120, 920, 740, "On-prem K8s — Azure Local (preview)", kind="local",
               sublabel="request-only")
arc = d.node(620, 260, az("other/arc-kubernetes.png"), "Arc extension\ninference operator",
             note="Model / ModelDeployment CRDs")
eng = d.box(620, 430, 290, 48, "ONNX-GenAI (CPU/GPU) or\nvLLM (GPU, high-throughput)")
gw = d.box(620, 550, 290, 52, "Service / Gateway API\nkey / Entra (disconnected: on-prem AD)")
d.edge(arc, eng)
d.edge(eng, gw)

c3 = d.cluster(950, 120, 1360, 740, "Air-gapped — disconnected containers", kind="local")
di = d.node(1080, 260, icon("container"), "Document Intelligence\ncontainer",
            note="the ONLY structured extraction on-prem")
oth = d.box(1080, 430, 300, 52, "Vision Read OCR / Speech /\nLanguage / Translator (gated)")
cu = d.box(1080, 560, 300, 52, "Content Understanding:\nNO container -> impossible on-prem")

d.footer(
    notes=[
        "Foundry Local: no embedding/vision models listed; server use explicitly rejected "
        "(no batching / GPU sharing) -> concurrent users need a real inference server (vLLM etc.).",
        "Azure Local flavor: 18 regions incl. Japan East; disconnected mode = expansion pack + "
        "local registry + cert-manager; default worker size 'usually too small' (official).",
        "Disconnected containers: approval form (~10 business days), works only on the approved "
        "subscription. Content Safety container docs are inconsistent -> verify before air-gap deals.",
    ],
    auth=[
        "Auth: device = none (local) / Azure Local connected = Entra, disconnected = on-prem AD "
        "(Contributor role includes data-plane inference - broader than cloud RBAC)",
    ],
    config_note="Source: docs/survey/architecture/07 §9",
)

d.save(str(_here.parent.parent / "images" / "d3-edge-onprem.png"))

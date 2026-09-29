"""services-agency(Port 13)のアーキテクチャ図(v2 スタイル: 日本語+処理順バッジ)。

Regenerate(labs/maf-ports で):  uv run --with diagrams,pillow python ports/services-agency/docs/architecture.py
"""

import sys
from pathlib import Path

_here = Path(__file__).resolve()
for _p in _here.parents:
    if (_p / "tools" / "archdiagram.py").exists():
        sys.path.insert(0, str(_p / "tools"))
        break
from archdiagram import BLUE, MUTED, NOTE_SHARED_ONLY_JA, TELEM, Diagram, icon, std_azure

d = Diagram(
    "services-agency — 通信グラフ制約つきの相談型協調(Port 13)",
    width=1500,
    height=900,
    subtitle="Agency Swarm の communication_flows を移植: 相談相手は LLM が実行時に選ぶが、許可された有向ペアのみ"
    "(agent-as-tool。応答は呼び出し元に戻る)",
)

# --- ローカル PC ---------------------------------------------------------------
local = d.cluster(40, 100, 860, 665, "ローカル PC(uv + MAF)", kind="local")
ag = d.cluster(200, 145, 840, 548, "Agency(agent-as-tool・深度上限 3)", kind="focus")

cli = d.node(112, 300, icon("cli"), "CLI\nservices-agency-maf")
ceo = d.box(480, 215, 200, 50, "CEO(Project Director)\n+ analyze_project")
cto = d.box(330, 345, 190, 50, "CTO\n+ create_technical_spec")
pm = d.box(630, 345, 170, 44, "Product Manager")
dev = d.box(480, 470, 150, 44, "Lead Developer")
cm = d.box(752, 470, 150, 44, "Client Success")
d.text(520, 512, "矢印 = 許可された有向ペア 7 本(矢印の無いペアには talk_to_* ツール自体が無い)",
       fill=MUTED, anchor="ma")

state = d.box(340, 615, 300, 46, "ProjectState(共有状態)\nproject_analysis / technical_specification")
commlog = d.box(660, 615, 250, 46, "CommLog(全通信の記録)\nstderr / レポート / JSON")

# 許可された有向ペア(talk_to_* ツールが生成される 7 本。ceo→cto と cto→dev は下の番号付きエッジ)
d.edge(ceo.port("bottom", 0.5), dev)
d.edge(ceo.port("bottom", 0.85), pm.port("top", 0.35))
d.edge(ceo.port("right"), cm, via=[(815, 215), (815, 470)])
d.edge(pm.port("bottom", 0.25), dev.port("top", 0.85))
d.edge(pm.port("bottom", 0.85), cm.port("top", 0.3))

# --- Azure(共有基盤のみ) ----------------------------------------------------------
az = std_azure(d, x0=900, y0=100, x1=1460, y1=665, base="mafportsw3", rg="rg-maf-ports-w3", ja=True,
               model_note="5 役で共用")
model, appi = az["model"], az["appi"]

# --- 処理の流れ ------------------------------------------------------------------
d.edge(cli, ag.port("left", 0.39), step=1, label="5 ターン", label_t=0.4, label_pos="above")
d.edge(ceo.port("bottom", 0.15), cto.port("top", 0.6), step=2, label="talk_to_cto", label_color=BLUE,
       label_t=0.45, label_pos="left")
d.edge(cto.port("bottom", 0.25), dev.port("left", 0.5), via=[(282.5, 470)], step=3, label="入れ子の相談",
       label_t=0.35, label_pos="left")
d.edge((840, 276), model, step=4, label="推論", label_color=BLUE, label_t=0.3, label_pos="above")
d.edge((660, 548), commlog, step=5, label_t=0.5)
d.edge((340, 548), state, label="読み書き", label_t=0.5, label_dx=34, label_dy=0, both=True)
d.edge((860, 557), appi, style="dashed", color=TELEM, label="OTel トレース", label_t=0.5, label_dy=-12)

d.steps_panel(40, 695, 1460, [
    "CLI が案件を 5 役に順に渡す(5 ターン)",
    "CEO が相談相手を選び talk_to_* を呼ぶ",
    "相談は入れ子に(深度を数え、上限 3)",
    "相談のたびに相手の Agent.run が推論",
    "応答は呼び出し元へ戻り、通信は CommLog へ",
], columns=3)

d.notes(
    [
        ("運用", NOTE_SHARED_ONLY_JA),
        ("制約", "許可 7 ペア以外は talk_to_* を生成しない(構造制約)。深度超過は例外でなくブロック通知を return"),
        ("実測", "トレースは execute_tool talk_to_* の下に相手の invoke_agent が入れ子(2026-07-31 ライブ・75 秒)"),
        ("認証", "モデル = API キー(ラボの .env)/ トレース = App Insights 接続文字列。外部サービスは使わない"),
        ("閉域", "ラボ構成: パブリックエンドポイント・VNet なし(閉域版は survey architecture 07)"),
    ],
    source="出典: labs/maf-ports/ports/services-agency/README.md",
)

d.save(str(_here.parent / "architecture.png"))

"""research-handoff(Port 3)のアーキテクチャ図(v2 スタイル: 日本語+処理順バッジ)。

Regenerate:  uv run --with diagrams,pillow python ports/research-handoff/docs/architecture.py
"""

import sys
from pathlib import Path

_here = Path(__file__).resolve()
_tools = next(p / "tools" for p in _here.parents if (p / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_tools))
from archdiagram import BLUE, TELEM, Diagram, icon, std_azure

d = Diagram(
    "research-handoff — トリアージ+switch-case handoff(Port 3)",
    width=1500,
    height=860,
    subtitle="委譲先を構造化出力(TriageDecision.handoff_to)で返させ、add_switch_case_edge_group で分岐する"
    "(HandoffBuilder は不採用 — README の再評価参照)",
)

# --- ローカル端末(MAF ワークフロー) ---------------------------------------------
local = d.cluster(40, 100, 770, 440, "ローカル端末(uv + MAF)", kind="local")
wf = d.cluster(200, 150, 750, 420, "MAF ワークフロー(switch-case エッジ)", kind="focus")

row = 255
cli = d.node(115, row, icon("cli"), "CLI", note="research-handoff-maf")
triage = d.box(315, row, 150, 56, "トリアージ\nTriageDecision")
editor = d.box(655, row, 150, 56, "エディタ\nResearchReport")
research = d.box(485, 355, 170, 56, "リサーチ\nsearch_web / save_fact")
d.text(475, 190, "委譲判断(先・理由)は HandoffDecided で CLI に表示", anchor="ma")
d.edge(triage, editor, label="Default: 直行", label_t=0.5, label_dy=-12)

# --- 外部 Web(Azure 外) -----------------------------------------------------------
d.cluster(40, 470, 770, 610, "外部 Web(Azure 外)", kind="external")
ddg = d.node(485, 525, icon("browser"), "DuckDuckGo HTML", note="キーレス")

# --- Azure(共有基盤) ------------------------------------------------------------
shared = std_azure(d, x0=800, y0=100, x1=1460, y1=610, foundry_h=250, ja=True)
model, appi = shared["model"], shared["appi"]

# --- 処理の流れ ----------------------------------------------------------------------
d.edge(cli, triage, step=1, label_t=0.5)
d.edge(triage.port("bottom"), research, via=[(triage.cx, research.cy)], step=2,
       label="Case: research", label_t=0.45, label_pos="left")
d.edge(research, ddg, step=3, label="検索", label_t=0.62, label_pos="left")
d.edge(research.port("right"), editor, via=[(editor.cx, research.cy)], step=4,
       label="要約+ファクト", label_t=0.3, label_pos="above")
d.edge(wf.port("right", (model.cy - wf.y0) / (wf.y1 - wf.y0)), model, step=5,
       label="推論(api-key)", label_color=BLUE, label_t=0.35, label_pos="above")
d.edge(local.port("right", 0.97), appi, via=[(785, local.port("right", 0.97)[1]), (785, appi.cy)],
       style="dashed", color=TELEM, step=6, label="OTel", label_color=TELEM, label_t=0.8,
       label_pos="above")

d.steps_panel(40, 640, 1460, [
    "CLI のトピックでトリアージが計画と委譲先を返す",
    "handoff_to で分岐(Case: research / Default: 直行)",
    "search_web でキーレス検索し、ファクトを保存",
    "要約+保存ファクトを editor のプロンプトへ",
    "3 役割とも共有モデル。triage / editor は構造化出力",
    "委譲・ツール呼び出しもスパンとして送信",
], columns=3)

d.notes(
    [
        ("制約", (
            "HandoffBuilder(orchestrations 1.2.0)は不採用を維持: 参加者は実 Agent 限定・"
            "既定 human-in-loop・型付きの最終出力なし"
        )),
        ("課金", "トークン従量のみ。Web 検索はキーレス DDG(Azure リソースなし)。editor 直行は呼び出し 2 回で最安"),
        ("認証", "モデル = api-key(lab の .env)/ DDG = 認証なし / トレース = App Insights 接続文字列"),
        ("閉域", "ラボ構成: 共有基盤のみ・パブリックエンドポイント・VNet なし(閉域版は survey architecture 07)"),
        ("実測", (
            "2026-07-31 ライブ: research 分岐 → 1,684 語のレポート、search_web ×8・save_important_fact ×5。"
            "2026-09-29 に core 1.19 / openai 3.20 でオフライン再確認"
        )),
    ],
    source="出典: labs/maf-ports/ports/research-handoff/README.md",
)

d.save(str(_here.parent / "architecture.png"))

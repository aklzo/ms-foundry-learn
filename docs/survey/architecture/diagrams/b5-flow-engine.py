"""B5: 業務フローエンジン主導(Logic Apps / Copilot Studio、05章)のアーキテクチャ図(v2 スタイル)。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/b5-flow-engine.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import BLUE, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "B5: 業務フローエンジン主導 — Logic Apps / Copilot Studio + Foundry を部品として使う",
    width=1500,
    height=800,
    subtitle="承認・通知・SaaS 連携が処理の主役で、AI は判断の一部だけを担う。"
    "業務部門がフローを保守したい場合の構成",
)

# --- 業務部門・M365(Azure 外・左) ------------------------------------------------------
d.cluster(40, 110, 250, 575, "業務部門・M365", kind="external")
biz = d.node(145, 215, res("onprem/client/users.png"), "業務部門", note="デザイナーで保守")
cs = d.node(145, 470, az("integration/power-platform.png"), "Copilot Studio")

# --- Azure ------------------------------------------------------------------------
d.cluster(280, 100, 1200, 585, "Azure サブスクリプション", kind="azure")

d.cluster(300, 140, 1180, 310, "Logic Apps(フローの主役)", kind="focus")
loop = d.node(700, 215, az("integration/logic-apps.png"), "agent loop ワークフロー", note="自律型 / 対話型")
conn = d.box(1005, 215, 230, 50, "1,400+ コネクタ\n(承認・通知・SaaS)")

d.cluster(300, 350, 1180, 565, "Foundry プロジェクト", kind="sub", sublabel="判断の部品")
agent = d.node(700, 470, icon("foundry"), "Foundry エージェント", note="prompt / hosted")

# --- 外部(Azure 外・右) -------------------------------------------------------------
d.cluster(1230, 110, 1460, 310, "SaaS / 基幹", kind="external")
saas = d.node(1345, 215, icon("browser"), "SaaS / 基幹 API")
d.cluster(1230, 350, 1460, 575, "公開先", kind="external")
teams = d.node(1345, 470, res("saas/chat/teams.png"), "Teams /\nM365 Copilot")

# --- 処理の流れ(下段) ----------------------------------------------------------------
d.steps_panel(40, 612, 1460, [
    "業務イベントでフローが起動(業務部門が保守)",
    "判断部分は Foundry をモデルソースに使う",
    "コネクタで承認・通知・SaaS 操作を実行",
    "Copilot Studio から Foundry エージェントを呼ぶ",
    "Foundry エージェントを Teams / M365 Copilot に公開",
], columns=3)

# --- edges ------------------------------------------------------------------------
d.edge(biz, loop, step=1, label_t=0.45)
d.edge((684, 292), (684, 436), color=BLUE, step=2, label="モデルソース\n(マネージド ID)",
       label_color=BLUE, label_t=0.6, label_pos="left")
d.edge((716, 436), (716, 292), label="ワークフローを\nアクションとして呼ぶ", label_t=0.4, label_dx=66, label_dy=0)
d.edge(loop, conn)
d.edge(conn, saas, step=3, label_t=0.5)
d.edge(cs, agent, step=4, label_t=0.45)
d.pill(398, 446, "Preview", anchor="mm")
d.edge(agent, teams, step=5, label_t=0.5)
d.pill(1022, 446, "GA", anchor="mm")

d.notes(
    [
        ("注意", "CAF: ローコードは重いカスタマイズで限界に達し移行が要る → 最初から複雑さが見えるなら Logic Apps / Copilot Studio で始めない"),
        ("制約", "Copilot Studio → Foundry はプレビュー。新ポータルのエージェントのみ + Activity プロトコルを REST / SDK で有効化(未有効は実行時 400)"),
        ("推奨", "Teams / M365 Copilot に出すだけなら GA の公開フロー(Foundry → M365)を使い、プレビューの逆向き接続に依存しない"),
        ("認証", "Logic Apps → Foundry はマネージド ID。逆に Foundry エージェントからワークフローをアクションとして呼べる"),
        ("課金", "Logic Apps は実行課金。prompt agent は推論 + ツールのみ(コンピュート課金なし)"),
    ],
    source="出典: docs/survey/architecture/05 B5",
)

d.save(
    str(_here.parent.parent / "images" / "b5-flow-engine.png"),
    slide=str(_here.parent.parent / "images" / "slide" / "b5-flow-engine.png"),
)

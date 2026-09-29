"""B3: 長時間・確実な再開(MAF + Durable Extension + DTS、05章)のアーキテクチャ図(v2 スタイル)。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/b3-durable.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import BLUE, STATUS_COLORS, TELEM, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "B3: 長時間・確実な再開 ── MAF + Durable Extension + DTS",
    width=1560,
    height=860,
    subtitle="数日かかる承認・外部バッチ待ち・失敗したステップからの再開。「MAF では無理だから LangGraph へ」と"
    "決める前に確認する",
)

R_A, R_C, R_D = 205, 350, 495  # workflow rows (受付 / 待機 / 実行)

# --- 業務チャネル・外部システム(Azure 外・左) -----------------------------------------
d.cluster(40, 110, 215, 440, "業務チャネル", kind="external")
ui = d.node(128, R_A, res("saas/chat/teams.png"), "業務 UI / Teams")
approver = d.node(128, R_C, res("onprem/client/user.png"), "承認者")
d.cluster(40, 460, 215, 625, "外部システム", kind="external")
batch = d.node(128, 530, icon("browser"), "基幹バッチ", note="完了を通知")

# --- Azure --------------------------------------------------------------------
d.cluster(240, 100, 1520, 640, "Azure サブスクリプション", kind="azure")
host = d.cluster(260, 140, 930, 625, "Azure Functions ホスト", kind="focus",
                 sublabel="または自前コンピュート / scale-to-zero")

wf_a = d.box(440, R_A, 250, 58, "MAF エージェント / ワークフロー\n(コアロジックは変更しない)")
wf_c = d.box(440, R_C, 250, 56, "待機(RequestInfo)\n承認・外部完了を数日でも待つ",
             fill=(255, 248, 230), border=(196, 140, 40))
wf_d = d.box(440, R_D, 250, 56, "再開 → 実行・監査記録\n(待機点から続行)")

ext = d.box(790, 350, 190, 380, "Durable Extension\n\nステップごとに\n自動チェックポイント\n\n障害・再デプロイ後も\n最後の CP から再開",
            fill=(255, 255, 255))
pv_text, pv_bg = STATUS_COLORS["Preview"]
d.pill(ext.x1 - 12, ext.y0, "beta", color=pv_text, bg=pv_bg, anchor="mm")

dts = d.node(1110, 350, icon("scheduler"), "Durable Task\nScheduler(DTS)", note="推奨バックエンド・フルマネージド")
dash = d.node(1395, 350, az("general/dashboard.png"), "DTS ダッシュボード", note="セッション / 進行を可視化")
state = d.box(1110, 540, 250, 56, "耐久状態(thread ID ごと)\n再起動・別インスタンスでも保持")

# --- 処理の流れ(下段) ------------------------------------------------------------
d.steps_panel(40, 662, 1520, [
    "業務 UI から依頼し、ワークフローを開始",
    "ステップごとの状態を DTS に保存(障害時は復元)",
    "承認者へ依頼し、数時間〜数日でも待つ",
    "承認・外部完了のイベントで待機点から再開",
], columns=2)

# --- edges --------------------------------------------------------------------
d.edge(ui, wf_a, step=1, label_t=0.42)
d.edge(wf_a, wf_c)
d.edge(wf_c.port("left"), approver, color=BLUE, both=True, step=3, label_t=0.81)
d.edge(batch, wf_c.port("left", 0.8), via=[(288, batch.cy), (288, wf_c.y0 + (wf_c.y1 - wf_c.y0) * 0.8)])
d.text(298, 436, "完了イベント", anchor="lt", fill=(70, 70, 70))
d.edge(wf_c, wf_d, step=4, label_t=0.5)
for b in (wf_a, wf_c, wf_d):
    d.edge(b.port("right"), (ext.x0, b.cy))
d.edge(ext, dts, both=True, step=2, label="保存 / 復元", label_t=0.45, label_pos="above")
d.edge(dts, dash, style="dashed", color=TELEM)
d.edge(dts, state)

d.notes(
    [
        ("推奨", "バックエンドは DTS(最高性能・フルマネージド・組込みダッシュボード)。ローカル エミュレータがあり CI でテストしやすい"),
        ("制約", "hosted agent の中から DTS を使う公式パターンは未確認 → Durable が要るなら Functions か自前コンピュートにホストする"),
        ("注意", "拡張パッケージ(agent-framework-durabletask / -azurefunctions)は 1.0.0b の beta。MAF 本体は GA"),
        ("注意", "hosted agent 内で完結させる代替は long-running hosted agents(Preview・DTS とは別系統)。AI が 1 ステップだけなら B5 を検討"),
        ("運用", "分散ホストで信頼性のあるストリーミングをするには Redis 等の stream broker が別途必要"),
    ],
    source="出典: docs/survey/architecture/05 B3(beta 表記は 02 章 H)",
)

d.save(
    str(_here.parent.parent / "images" / "b3-durable.png"),
    slide=str(_here.parent.parent / "images" / "slide" / "b3-durable.png"),
)

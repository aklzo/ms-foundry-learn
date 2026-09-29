"""B2: 承認付き業務自動化 HITL(05章)のアーキテクチャ図(v2 スタイル: 日本語+処理順バッジ)。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/b2-hitl-automation.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import BLUE, TELEM, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "B2: 承認付き業務自動化(HITL)— MAF hosted agent",
    width=1560,
    height=800,
    subtitle="調査 → 実行案 → 人が承認 → 実行 → 監査。分岐・待機・再開を含むため prompt agent では表現できず、"
    "コードファースト(MAF ワークフロー)で組む",
)

# --- 業務チャネル(Azure 外・左) ------------------------------------------------
d.cluster(40, 110, 280, 560, "業務チャネル", kind="external")
teams = d.node(160, 215, res("saas/chat/teams.png"), "業務 UI / Teams")
user = d.node(160, 384, res("onprem/client/user.png"), "承認者")

# --- Azure --------------------------------------------------------------------
d.cluster(305, 100, 1325, 625, "Azure サブスクリプション", kind="azure")
d.cluster(325, 140, 1060, 575, "Foundry プロジェクト", kind="sub")
ha = d.cluster(345, 180, 825, 555, "Hosted agent(MAF ワークフロー)", kind="focus")

hosted = d.node(415, 265, icon("containerapp"), "エージェント\nコンテナ", note="Entra Agent ID", status="GA")
triage = d.box(575, 250, 118, 40, "受付・振り分け")
research = d.box(740, 250, 118, 40, "調査(RAG)")
proposal = d.box(740, 370, 118, 40, "実行案の作成")
hitl = d.box(575, 370, 132, 48, "承認待ち\n(RequestInfo)", fill=(255, 248, 230), border=(196, 140, 40))
execute = d.box(575, 490, 118, 40, "実行(ツール)")
audit = d.box(740, 490, 118, 40, "監査記録")
d.edge(triage, research)
d.edge(research, proposal)
d.edge(proposal, hitl)
d.edge(hitl, execute, label="承認", label_t=0.45, label_dx=-26, label_dy=0)
d.edge(execute, audit)

model = d.node(945, 285, icon("model"), "モデルデプロイ", status="GA")
appi = d.node(945, 425, icon("appinsights"), "App Insights", note="接続文字列は自動注入")

apim = d.node(1195, 215, az("integration/api-management.png"), "APIM / Toolbox(MCP)", note="ツールの統制",
              status="GA")
store = d.node(1195, 530, az("databases/azure-cosmos-db.png"), "監査ストア", note="Cosmos DB 等・自前で保持")

# --- 基幹システム(Azure 外・右) -------------------------------------------------
d.cluster(1350, 110, 1520, 560, "基幹システム", kind="external", sublabel="")
erp = d.node(1435, 215, icon("browser"), "業務 API /\nLogic Apps", note="オンプレ / SaaS")

# --- 処理の流れ(下段) ------------------------------------------------------------
d.steps_panel(40, 655, 1520, [
    "業務 UI から依頼(Responses API)",
    "調査・実行案の作成でモデルを呼ぶ",
    "承認待ちで停止し、承認者へ依頼",
    "承認後、MCP 経由で基幹システムを操作",
    "誰が・いつ・何を承認したかを自前ストアへ",
], columns=3)

# --- edges --------------------------------------------------------------------
d.edge(teams, hosted, step=1, label_t=0.5)
d.edge(ha.port("right", 0.28), model, step=2, label="推論", label_t=0.4, label_pos="above")
d.edge(hitl.port("left", 0.8), user, color=BLUE, both=True, step=3, label="承認依頼 / 判断",
       label_color=BLUE, label_t=0.3, label_pos="below")
d.edge(ha.port("right", 0.093), apim, step=4, label="MCP ツール呼び出し", label_t=0.6, label_pos="above")
d.edge(apim, erp, label="API / コネクタ", label_t=0.5, label_dy=-12)
d.edge(audit, store, via=[(740, 530)], step=5, label="承認記録", label_t=0.6, label_pos="above")
d.edge(ha.port("right", 0.653), appi, style="dashed", color=TELEM, label="OTel トレース",
       label_t=0.5, label_dy=-12)

d.notes(
    [
        ("運用", "アイドル(既定 15 分・2〜60 分で設定可)で計算資源を解放し状態は保持。30 日無操作で完全削除"),
        ("制約", "数日単位の承認待ちは B3(Durable Extension + DTS)へ。hosted 内の長時間実行はプレビュー"),
        ("注意", "トレースは業務監査ログではない(ポータル表示 90 日・プロンプトや PII を含み得る)→ 承認記録は自前ストアに"),
        ("課金", "アクティブセッションの CPU + メモリで課金。サイズ過大は同時実行数で掛け算になる"),
        ("認証", "承認者 → 業務 UI は Entra ID / エージェント → Entra Agent ID(エージェント単位)/ 基幹ツールは APIM で OBO か app-only をツールごとに決める"),
    ],
    source="出典: docs/survey/architecture/05 B2",
)

d.save(
    str(_here.parent.parent / "images" / "b2-hitl-automation.png"),
    slide=str(_here.parent.parent / "images" / "slide" / "b2-hitl-automation.png"),
)

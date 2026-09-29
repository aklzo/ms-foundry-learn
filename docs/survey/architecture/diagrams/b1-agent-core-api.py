"""B1: 単一エージェント + 基幹 API(05章)のアーキテクチャ図(v2 スタイル: 日本語+処理順バッジ)。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/b1-agent-core-api.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import BLUE, F_CLUSTER, F_EDGE, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "B1: 単一エージェント + 基幹 API(参照系中心)",
    width=1560,
    height=860,
    subtitle="在庫照会・受発注状況・顧客参照。設計の本命は認可 ── agent identity(app-only)で叩くか、"
    "ログインユーザーの権限(OBO)で叩くか",
)

ROW = 215   # agent row
R1, R2 = 430, 545  # tool rows

# --- 利用者(左) ------------------------------------------------------------------
d.cluster(40, 110, 215, 625, "利用者", kind="external")
user = d.node(128, ROW, res("onprem/client/user.png"), "社員\n(Teams / 自社ポータル)", note="Entra ID")

# --- Azure --------------------------------------------------------------------
d.cluster(240, 100, 1240, 640, "Azure サブスクリプション", kind="azure")
fc = d.cluster(260, 140, 1000, 300, "Foundry プロジェクト", kind="sub")
agent = d.node(370, ROW, icon("project"), "Prompt agent", note="固有の agent identity", status="GA")
model = d.node(620, ROW, icon("model"), "モデルデプロイ")

tb = d.cluster(260, 355, 1000, 620, "Toolbox ── 単一の MCP 互換エンドポイント", kind="focus")
lw = d.d.textlength("Toolbox ── 単一の MCP 互換エンドポイント", font=F_CLUSTER)
d.pill(tb.x0 + 12 + lw + 8, tb.y0 + 17, "GA")
d.text(tb.x0 + 12 + lw + 50, tb.y0 + 10, "バージョニング + 集中認証")
functions = d.box(450, R1, 270, 54, "Azure Functions\nキュー経由・standard setup のみ")
aisearch = d.box(450, R2, 270, 54, "AI Search\n手順書・マスタ定義のグラウンディング", status="GA")
openapi = d.box(810, R1, 270, 54, "OpenAPI ツール\n匿名 / API キー / マネージド ID", status="GA")
mcp = d.box(810, R2, 270, 54, "MCP ツール\nEntra / OAuth ID パススルー(OBO)", status="GA")

apim = d.node(1120, R1, az("integration/api-management.png"), "APIM(社内)")

# --- Entra(右上)・基幹システム(右下) ---------------------------------------------
d.cluster(1265, 110, 1520, 335, "Microsoft Entra", kind="external")
entra = d.node(1392, ROW, icon("entra"), "Entra ID", note="Agent ID / OBO 交換")
d.cluster(1265, 355, 1520, 625, "基幹システム / SaaS", kind="external")
core = d.node(1392, R1, icon("browser"), "基幹 API", note="オンプレ / 社内")
saas = d.node(1392, R2, icon("browser"), "SaaS(ServiceNow 等)")

# --- 処理の流れ(下段) ------------------------------------------------------------
d.steps_panel(40, 662, 1520, [
    "社員が Entra ID でサインインして質問",
    "agent がモデルで呼ぶツールを決める",
    "Toolbox(単一の MCP エンドポイント)経由でツールを呼ぶ",
    "OpenAPI ツール → APIM → 基幹 API(MI か OBO)",
    "MCP ツールで SaaS を操作(OAuth OBO)",
], columns=3)

# --- edges --------------------------------------------------------------------
d.edge(user, agent, step=1, label_t=0.42)
d.edge(agent, model, step=2, label_t=0.5)
GUARD = "ガードレール介入(Tool call / response)"
d.edge(agent, (agent.cx, tb.y0), step=3, label=GUARD, label_t=0.5)
d.pill(agent.cx + 14 + d.d.textlength(GUARD, font=F_EDGE) + 8, (agent.y1 + tb.y0) / 2, "Preview")
d.edge((fc.x1, ROW), entra, label="トークン(app-only / OBO)", label_color=BLUE, color=BLUE, label_t=0.4,
       label_dy=-12)
d.edge(openapi, apim, step=4, label="MI / OBO", label_color=BLUE, label_t=0.6, label_pos="above")
d.edge(apim, core)
d.edge(mcp, saas, step=5, label="OAuth OBO", label_color=BLUE, label_t=0.3, label_pos="above")

d.notes(
    [
        ("認証", "対話型 = OBO(ユーザー委任)/ 無人 = agent identity の RBAC。割当先は agent identity(プロジェクト MI ではない)、audience は下流リソース ID"),
        ("認証", "新エージェントモデルは作成時に固有 identity(旧モデルは publish で ID が変わり RBAC 再割当)。本番の資格情報はフェデレーテッド一択"),
        ("制約", "hosted agent はツールを直付けできない(Toolbox 前提)→ コードファーストに進む予定なら最初から Toolbox で組む"),
        ("注意", "更新系は冪等キー + 金額・件数の上限チェックをツール側に置く。プロンプトの「10 万円以上は承認」は統制ではない"),
        ("注意", "Toolbox は GA だが prompt agent からの利用は Azure ブログが Preview と表記(要確認)。Azure Functions ツールも公式表記が矛盾(要確認)"),
    ],
    source="出典: docs/survey/architecture/05 B1",
)

d.save(
    str(_here.parent.parent / "images" / "b1-agent-core-api.png"),
    slide=str(_here.parent.parent / "images" / "slide" / "b1-agent-core-api.png"),
)

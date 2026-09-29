"""共有基盤(shared.bicep + roles.bicep)のアーキテクチャ図(v2 スタイル: 日本語+処理順バッジ)。

Regenerate:  uv run --with diagrams,pillow python infra/docs/architecture.py
"""

import sys
from pathlib import Path

_here = Path(__file__).resolve()
_tools = next(p / "tools" for p in _here.parents if (p / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_tools))
from archdiagram import BLUE, TELEM, Diagram, icon

d = Diagram(
    "maf-ports 共有基盤 — Foundry + 監視",
    width=1500,
    height=900,
    subtitle="infra/shared.bicep(1 回だけデプロイ・全 14 ポート共通)+ infra/roles.bicep(第 2 段: MI への RBAC)"
    "— Microsoft.CognitiveServices 2025-06-01",
)

# --- ローカル端末 ----------------------------------------------------------------------
d.cluster(40, 100, 380, 660, "ローカル端末", kind="local")
azcli = d.node(210, 190, icon("cli"), "az CLI + Bicep", note="shared.bicep → roles.bicep")
cli = d.node(210, 385, icon("cli"), "ポート CLI\n(ports/*・MAF)", note="configure_azure_monitor")

# --- Azure ------------------------------------------------------------------------------
azure = d.cluster(420, 100, 1460, 660, "Azure サブスクリプション — rg-maf-ports(Japan East)", kind="azure")
d.cluster(450, 150, 1090, 470, "Foundry: aif-<baseName>", kind="focus",
          sublabel="AIServices S0・公開ネットワーク・ローカル認証有効")
model = d.node(620, 250, icon("model"), "モデルデプロイ\ngpt-5.4-mini", note="GlobalStandard・容量 10",
               status="GA")
project = d.node(620, 385, icon("project"), "プロジェクト: maf-ports", note="システム割り当て MI",
                 status="GA")
account = d.node(935, 315, icon("foundry"), "Foundry アカウント", note="システム割り当て MI・api-key 有効")

rbac = d.node(1290, 315, icon("rbac"), "roles.bicep(第 2 段)\nロール割り当て ×4",
              note="OpenAI User + Foundry User")
d.text(1290, 414, "× アカウント MI / プロジェクト MI", anchor="ma")

appi = d.node(620, 560, icon("appinsights"), "App Insights\nappi-<baseName>")
logws = d.node(935, 560, icon("loganalytics"), "Log Analytics\nlog-<baseName>", note="PerGB2018・保持 30 日")
d.edge(appi, logws, label="ワークスペース", label_dy=-12)

# --- 処理の流れ ----------------------------------------------------------------------
d.edge(azcli, (azure.x0, azcli.cy), step=1, label="ARM デプロイ", label_t=0.5, label_pos="above")
d.edge(rbac, account, step=2, label="権限付与", label_t=0.45, label_pos="above")
d.edge(cli, model, step=3, label="api-key", label_color=BLUE, label_t=0.2, label_pos="above",
       color=BLUE)
d.edge(cli, project, step=4, label="Entra ID", label_color=BLUE, label_t=0.2, label_pos="below",
       color=BLUE)
d.edge((cli.cx, cli.y1 + 6), appi, via=[(cli.cx, appi.cy)], style="dashed", color=TELEM, step=5,
       label="OTel", label_color=TELEM, label_t=0.75, label_pos="above")
d.edge(project, appi, step=6, label="AppInsights 接続", label_t=0.5, label_pos="right")

d.steps_panel(40, 690, 1460, [
    "shared.bicep で基盤一式を作る(第 1 段・ARM)",
    "roles.bicep で MI 2 つにロール 4 件(第 2 段)",
    "ポートは v1 エンドポイントを api-key で呼ぶ",
    "一部ポートはプロジェクト EP を Entra ID で呼ぶ",
    "各ポートが OTel を App Insights へ直接送る",
    "プロジェクトの接続でポータルのトレースに表示",
], columns=3)

d.notes(
    [
        ("運用", (
            "2 段デプロイ: MI の principalId をパラメータで受けて割り当て名の guid に含める"
            " → 再デプロイで MI が変わっても孤児割り当てを残さない"
        )),
        ("認証", (
            "モデル = api-key(既定)/ プロジェクト EP = Entra ID(利用者に Foundry User)/"
            " Memory・評価 = MI + roles.bicep"
        )),
        ("課金", "すべて従量(トークン + 取り込み量)で待機コストなし。時間課金の部品はポート固有側(AI Search Basic 等)"),
        ("注意", "RBAC 伝播に 5〜15 分。RG 削除後も aif-<baseName> は 48 時間 soft delete(purge か baseName を変える)"),
        ("閉域", "ラボ構成: パブリックエンドポイント・VNet なし(閉域版は survey architecture 07)"),
    ],
    source="出典: labs/maf-ports/infra/docs/runbook.md",
)

d.save(str(_here.parent / "architecture.png"))

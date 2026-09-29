"""B4: マルチエージェント(専門分化、05章)のアーキテクチャ図(v2 スタイル: 日本語+処理順バッジ)。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/b4-multi-agent.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import BLUE, MUTED, RED, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "B4: マルチエージェント(専門分化)— MAF オーケストレータ + hosted agent",
    width=1560,
    height=800,
    subtitle="領域ごとにプロンプト・ナレッジ・権限を分けたい / 並列に調べさせたい場合に限る。"
    "多くの案件は単一エージェント + 複数ツールで足りる(→ 11章)",
)

# --- 利用者(Azure 外・左) ----------------------------------------------------------
d.cluster(40, 110, 230, 640, "利用者", kind="external")
user = d.node(135, 385, res("onprem/client/user.png"), "業務アプリ / 利用者")

# --- Azure --------------------------------------------------------------------------
d.cluster(280, 100, 1290, 670, "Azure サブスクリプション", kind="azure")
d.cluster(300, 140, 1010, 650, "Foundry プロジェクト", kind="sub")

d.cluster(320, 180, 560, 490, "オーケストレータ", kind="sub")
patterns = d.box(440, 250, 200, 62, "Sequential・Concurrent\nHandoff・Group chat\nMagentic(5 パターン組込み)")
orch = d.node(440, 385, icon("workflow"), "MAF ワークフロー", note="hosted agent として配置", status="GA")

legacy = d.box(440, 575, 176, 44, "ポータルの\nビジュアル Workflows", fill=(242, 243, 245),
               border=(170, 174, 180), text_color=MUTED, status="廃止予定")
d.text(440, 606, "2026-12-01 廃止", fill=RED, anchor="ma")

d.cluster(605, 180, 865, 460, "専門エージェント", kind="focus", sublabel="hosted agent")
ops = d.node(735, 250, icon("containerapp"), "業務エージェント", note="個別 Agent ID・更新系", note_color=BLUE)
res_agent = d.node(735, 385, icon("containerapp"), "調査エージェント", note="個別 Agent ID・参照のみ",
                   note_color=BLUE)
a2a = d.box(735, 540, 150, 40, "A2A ツール(v1.0)", status="GA")

apim = d.node(1150, 250, az("integration/api-management.png"), "APIM / Toolbox(MCP)", note="ツールの統制",
              status="GA")
search = d.node(1150, 385, icon("search"), "領域別ナレッジ", note="AI Search / Foundry IQ")

# --- 外部(Azure 外・右) ------------------------------------------------------------
d.cluster(1320, 110, 1520, 330, "基幹システム", kind="external")
erp = d.node(1420, 250, icon("browser"), "業務 API")
d.cluster(1320, 420, 1520, 640, "他組織", kind="external")
partner = d.node(1420, 540, icon("project"), "パートナーの\nエージェント")

# --- 処理の流れ(下段) ------------------------------------------------------------------
d.steps_panel(40, 700, 1520, [
    "業務アプリから依頼(Responses API)",
    "MAF がパターンに沿って専門エージェントへ振り分け",
    "各エージェントが自分の ID・権限でツール / ナレッジを使う",
    "他組織のエージェントへは A2A v1.0 で委譲",
], columns=2)

# --- edges --------------------------------------------------------------------------
d.edge(user, orch, both=True, step=1, label_t=0.36)
d.edge(orch, ops)
d.edge(orch, res_agent, step=2, label_t=0.5)
d.edge(orch, a2a)
d.edge(legacy.port("top"), (440, 490), color=MUTED, label="YAML を移行", label_t=0.5,
       label_dx=48, label_dy=0)
d.edge(ops, apim, step=3, label_t=0.5)
d.edge(apim, erp)
d.edge(res_agent, search, step=3, label_t=0.5)
d.edge(a2a, partner, color=BLUE, step=4, label="Entra 必須", label_color=BLUE, label_t=0.5,
       label_pos="above")

d.notes(
    [
        ("期限", "ビジュアル Workflows は 2026-12-01 廃止。デザイナーが消える前に YAML をエクスポート → MAF(推奨)/ Logic Apps / A2A"),
        ("認証", "hosted agent はエージェントごとに Entra Agent ID。prompt agent は旧モデルだとプロジェクト共通 ID(agent.identity で確認)"),
        ("制約", "A2A は未指定だと v0.3(プレビュー)→ A2A-Version: 1.0 を明示。テキストのみ・SSE 非対応・呼び出し側に Foundry Agent Consumer"),
        ("注意", "セキュリティトリミングは全エージェントで実装(公式)。並列エージェント間で可変状態を共有しない"),
        ("推奨", "Connected agents は新 Agent Service で非対応 → 新規設計は A2A か MAF に寄せる"),
    ],
    source="出典: docs/survey/architecture/05 B4",
)

d.save(
    str(_here.parent.parent / "images" / "b4-multi-agent.png"),
    slide=str(_here.parent.parent / "images" / "slide" / "b4-multi-agent.png"),
)

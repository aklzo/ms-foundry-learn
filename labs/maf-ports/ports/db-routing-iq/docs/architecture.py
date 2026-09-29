"""db-routing-iq(Port 10)のアーキテクチャ図(v2 スタイル: 日本語+処理順バッジ)。

Regenerate(labs/maf-ports で):
    uv run --with diagrams,pillow python ports/db-routing-iq/docs/architecture.py
"""

import sys
from pathlib import Path

_here = Path(__file__).resolve()
_tools = next(p / "tools" for p in _here.parents if (p / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_tools))

from archdiagram import BLUE, ORANGE, TELEM, Diagram, icon, std_azure

d = Diagram(
    "db-routing-iq — Foundry IQ で複数ソースを振り分け(Port 10)",
    width=1560,
    height=1100,
    subtitle="元アプリの三段カスケード(類似度比較 → LLM ルート → Web)のうち前二段を knowledge base の"
    "宣言に移し、エージェントは MCP で KB を呼ぶだけ。Web fallback だけがアプリに残る",
)

# --- ローカル(uv + MAF) -----------------------------------------------------------
local = d.cluster(40, 100, 560, 570, "ローカル PC(uv + MAF)", kind="local")
cli = d.node(105, 230, icon("cli"), "CLI\ndb-routing-iq-maf")
agent = d.box(330, 230, 190, 56, "db_routing_agent\n(MAF Agent)")
web = d.box(185, 440, 170, 48, "web_search\n(自前 DuckDuckGo)")
mcp = d.box(430, 440, 230, 56, "MCPStreamableHTTPTool\nknowledge_base_retrieve")
setup = d.box(405, 520, 260, 38, "scripts/setup_kb.py(事前に 1 回)")

ext = d.cluster(40, 600, 320, 725, "外部(Azure 外)", kind="external")
ddg = d.node(web.cx, 655, icon("browser"), "DuckDuckGo HTML", icon_size=44)

# --- Azure ----------------------------------------------------------------------------
shared = std_azure(
    d, x0=600, y0=100, x1=1520, y1=740, base="mafportsw2", foundry_h=185, ja=True,
    model_note="回答生成 + KB 内のプランニング",
)
srch = d.cluster(630, 355, 1490, 545, "AI Search(Basic)", kind="focus")
mcpend = d.box(720, 440, 150, 56, "MCP エンドポイント\n(KB ごとに 1 つ)")
d.text(720, 476, "api-key ヘッダー\n(static_headers)", fill=BLUE, anchor="ma")
kb = d.box(shared["model"].cx, 440, 150, 56, "knowledge base\n(LLM プランニング)",
           status="Preview")
ks = d.box(1170, 440, 220, 56, "knowledge source ×3\n→ 索引 ×3(製品/サポート/財務)")
svc = d.node(1405, 430, icon("search"), "srch-mafportsw2-iq\nBasic・1 レプリカ", note="約 $0.10/時",
             note_color=ORANGE)

# --- 辺 ----------------------------------------------------------------------------
d.edge(cli, agent)
d.edge(agent, mcp, label="まず KB", label_t=0.5, label_dx=34, label_dy=0)
d.edge(agent, web, label="空振り時のみ", label_t=0.55, label_dx=-44, label_dy=0)
d.edge(setup.port("right"), (srch.x0, setup.cy), step=1, label="REST", label_t=0.3,
       label_pos="above")
d.edge(mcp, mcpend, step=2, label_t=0.7)
d.edge(mcpend, kb)
d.edge(kb, shared["model"], step=3, label="LLM でソース選択(effort=low)", label_t=0.45,
       label_pos="right")
d.edge(kb, ks, step=4, label="副クエリ並列 + L2", label_t=0.5, label_pos="below", label_dy=16)
d.edge(web, ddg, step=5, label="HTTPS", label_t=0.4, label_pos="left")
d.edge(agent.port("right", 0.3), shared["model"], step=6, label="api-key", label_color=BLUE,
       label_t=0.7, label_pos="above")
d.edge(local.port("right", 0.97), shared["appi"], style="dashed", color=TELEM,
       label="OTel トレース", label_t=0.55, label_dy=-12)

# --- 処理の流れ(下段) ----------------------------------------------------------------
d.steps_panel(40, 770, 1520, [
    "事前に setup_kb.py が索引・KS・KB を作成",
    "エージェントがまず KB を MCP で呼ぶ",
    "KB が LLM でソースを選ぶ(Preview 機能)",
    "3 ソースへ副クエリを並列発行し L2 で並べ替え",
    "KB が空振りのときだけ web_search へ",
    "モデルが出典付きの回答を組み立てる",
], columns=3)

d.notes(
    [
        ("制約", ("LLM によるソース選択は Search REST のプレビュー(2026-08-01-preview)のみ。"
                  "GA の 2026-04-01 は最小の抽出検索だけ")),
        ("課金", ("AI Search Basic は時間課金(約 $0.10/時)→ 検証後は RG ごと削除。"
                  "KB 内プランニングのトークンも自分のデプロイに課金")),
        ("認証", ("MCP は api-key を static_headers で付与(同一オリジン限定・MAF 1.19)。"
                  "本番は Bearer + Search Index Data Reader")),
        ("実測", ("2026-07-31 ライブ 4 問 37.3 秒: アプリ側のルーティングコードなしで 3 ドメイン + "
                  "Web fallback が成立(当時 2026-05-01-preview)")),
        ("注意", ("ラボ構成: パブリックエンドポイント・VNet なし(閉域版は survey architecture 07)。"
                  "DuckDuckGo は Azure 外へのデータフロー")),
    ],
    source="出典: labs/maf-ports/ports/db-routing-iq/README.md",
)

d.save(str(_here.parent / "architecture.png"))

"""A5: Foundry IQ / agentic retrieval(04章)のアーキテクチャ図(v2 スタイル: 日本語+処理順バッジ)。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/a5-foundry-iq.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import BLUE, ORANGE, STATUS_COLORS, Diagram, icon, res  # noqa: E402

d = Diagram(
    "A5: 複数ソース横断・高精度 ── Foundry IQ(agentic retrieval)",
    width=1560,
    height=880,
    subtitle="knowledge base を共有ナレッジ層にして MCP で公開する。Foundry agent も MAF / LangGraph / 自作アプリも"
    "同じナレッジを使える",
)

ROW = 225   # agent row
PIPE = 260  # retrieval pipeline row

# --- 利用側(左) ------------------------------------------------------------------
d.cluster(40, 110, 225, 628, "利用側", kind="external")
user = d.node(132, ROW, res("onprem/client/user.png"), "社員")
maf = d.node(132, 530, icon("cli"), "MAF / LangGraph /\n自作アプリ", note="同じ KB を MCP で")

# --- Azure --------------------------------------------------------------------
d.cluster(250, 100, 1520, 640, "Azure サブスクリプション", kind="azure")
d.cluster(270, 140, 455, 330, "Foundry プロジェクト", kind="sub")
agent = d.node(362, ROW, icon("project"), "Foundry agent", note="structured input")
model = d.node(362, 415, icon("model"), "Azure OpenAI\nデプロイ", note="計画・合成トークン", note_color=ORANGE)

sc = d.cluster(560, 140, 1500, 625, "Azure AI Search(必須)", kind="focus", sublabel="agentic retrieval エンジン")
kb = d.box(640, 380, 140, 370, "knowledge base\n\nMCP エンドポイント\n(GA 版 API でも可\n= 抽出のみ)",
           fill=(255, 255, 255))
pv_text, pv_bg = STATUS_COLORS["Preview"]
d.pill(kb.x1 - 14, kb.y0, "一部 GA", color=pv_text, bg=pv_bg, anchor="mm")

plan = d.box(850, PIPE, 150, 54, "クエリ計画\n(サブクエリに分解)", status="Preview")
retr = d.box(1055, PIPE, 150, 54, "並列検索\n(ソースごと)")
rank = d.box(1300, PIPE, 180, 54, "セマンティック再ランク\n→ 抽出 / 回答合成")
d.text(1300, PIPE + 34, "回答合成は Preview", fill=pv_text, anchor="ma")

src = d.cluster(735, 385, 1480, 595, "ナレッジソース(KB が束ねる)", kind="sub")
d.box(1107, 455, 700, 44, "searchIndex(既存インデックス)/ azureBlob / indexedOneLake / web(Bing)", status="GA")
d.box(1107, 543, 700, 44, "indexedSharePoint / remoteSharePoint / azureSql / file / mcpServer / workIQ / Fabric",
      status="Preview")

# --- 処理の流れ(下段) ------------------------------------------------------------
d.steps_panel(40, 656, 1520, [
    "社員が Foundry agent に質問",
    "agent が MCP で KB を呼ぶ(トークンはヘッダー)",
    "LLM がクエリをサブクエリに分解",
    "各ナレッジソースを並列に検索",
    "再ランクして抽出結果か合成回答を引用付きで返す",
], columns=3)

# --- edges --------------------------------------------------------------------
d.edge(user, agent, step=1, label_t=0.42)
d.edge(agent, (kb.x0, ROW), step=2, label="MCP + トークン", label_color=BLUE, label_t=0.62,
       label_pos="above")
d.pill(507, ROW + 22, "接続は Preview", color=pv_text, bg=pv_bg, anchor="mm")
d.edge(maf, (kb.x0, 530), label="MCP", label_t=0.62, label_dy=-12)
d.edge((kb.x0, 415), model, label="計画・合成", label_color=ORANGE, label_t=0.5, label_dy=-12)
d.edge((kb.x1, PIPE), plan, step=3, label_t=0.5)
d.edge(plan, retr)
d.edge(retr, (retr.cx, src.y0), step=4, label_t=0.5)
d.edge(retr, rank, step=5, label_t=0.5)

d.notes(
    [
        ("制約", "ポータルで作った構成は全部 Preview。GA は REST 2026-04-01 を直接叩く(minimal・抽出型のみ。合成回答は 2026-08-01-preview)"),
        ("制約", "KB の MCP は GA 版でも使えるが、Agent Service 側の RemoteTool 接続は Preview → agent から呼ぶ構成全体はまだ GA にならない"),
        ("制約", "GA 版には ingestionPermissionOptions がない → 「GA 構成 + 文書単位 ACL」は両立しない"),
        ("注意", "ユーザートークンを渡さないと権限付きソースも未フィルタで全件返る(エラーにならない)→ 呼び出し側でトークン必須チェック"),
        ("課金", "AI Search の knowledgeRetrieval トークン(月 5,000 万まで無料)+ AOAI の計画・合成トークン。S3 HD は古いサービスに非対応あり → 実機確認"),
    ],
    source="出典: docs/survey/architecture/04 A5",
)

d.save(
    str(_here.parent.parent / "images" / "a5-foundry-iq.png"),
    slide=str(_here.parent.parent / "images" / "slide" / "a5-foundry-iq.png"),
)

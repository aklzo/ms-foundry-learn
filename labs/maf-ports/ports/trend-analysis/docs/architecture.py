"""trend-analysis(Port 1)のアーキテクチャ図(v2 スタイル: 日本語+処理順バッジ)。

Regenerate:  uv run --with diagrams,pillow python ports/trend-analysis/docs/architecture.py
"""

import sys
from pathlib import Path

_here = Path(__file__).resolve()
_tools = next(p / "tools" for p in _here.parents if (p / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_tools))
from archdiagram import BLUE, NOTE_SHARED_ONLY_JA, TELEM, Diagram, icon, std_azure

d = Diagram(
    "trend-analysis — 逐次ワークフロー(Port 1)",
    width=1500,
    height=800,
    subtitle="収集 → 要約 → 分析の 3 段を MAF WorkflowBuilder の直列グラフに載せ、共有基盤の 1 モデルで実行する"
    "(agent-framework-core 1.19 / openai 3.x)",
)

# --- ローカル端末(MAF ワークフロー) ---------------------------------------------
local = d.cluster(40, 100, 770, 405, "ローカル端末(uv + MAF)", kind="local")
wf = d.cluster(215, 150, 750, 385, "MAF ワークフロー(WorkflowBuilder・直列)", kind="focus")

cli = d.node(125, 290, icon("cli"), "CLI\ntrend-analysis-maf")
collect = d.box(318, 290, 140, 56, "収集\nsearch_news")
summarize = d.box(482, 290, 140, 56, "要約\nread_article")
analyze = d.box(646, 290, 140, 56, "分析\n(ツールなし)")
d.edge(collect, summarize)
d.edge(summarize, analyze)
d.text(482, 205, "各段の完了は StageDone(intermediate)で CLI へ通知", anchor="ma")
d.text(646, 330, "出力: 3 節のレポート", anchor="ma")

# --- 外部 Web(Azure 外) -----------------------------------------------------------
d.cluster(40, 440, 770, 600, "外部 Web(Azure 外)", kind="external")
ddg = d.node(318, 510, icon("browser"), "DuckDuckGo HTML", note="キーレス")
sites = d.node(482, 510, icon("browser"), "記事サイト", note="httpx + BS4")

# --- Azure(共有基盤) ------------------------------------------------------------
shared = std_azure(d, x0=800, y0=100, x1=1460, y1=600, foundry_h=240, ja=True)
model, appi = shared["model"], shared["appi"]

# --- 処理の流れ ----------------------------------------------------------------------
d.edge(cli, collect, step=1, label_t=0.45)
d.edge(collect, ddg, step=2, label="検索", label_t=0.62, label_pos="left")
d.edge(summarize, sites, step=3, label="本文取得", label_t=0.62, label_pos="right")
d.edge(wf.port("right", (model.cy - wf.y0) / (wf.y1 - wf.y0)), model, step=4,
       label="推論(api-key)", label_color=BLUE, label_t=0.35, label_pos="above")
d.edge(local.port("right", 0.97), appi, via=[(785, local.port("right", 0.97)[1]), (785, appi.cy)],
       style="dashed", color=TELEM, step=5, label="OTel", label_color=TELEM, label_t=0.8,
       label_pos="above")

d.steps_panel(40, 630, 1460, [
    "CLI からトピックを渡して収集段を起動",
    "収集: search_news で DDG をキーレス検索",
    "要約: read_article で記事本文を取得",
    "3 段とも共有モデルを Responses API で呼ぶ",
    "段・エージェント・ツール単位のスパンを送信",
], columns=3)

d.notes(
    [
        ("課金", (
            "モデルのトークン従量のみ。検索はキーレス DDG で Azure の検索リソースなし"
            "(Foundry の Web search ツールは別課金・DPA 対象外のため不採用)"
        )),
        ("認証", "モデル = api-key(lab の .env)/ DDG・記事取得 = 認証なし / トレース = App Insights 接続文字列"),
        ("運用", NOTE_SHARED_ONLY_JA),
        ("閉域", "ラボ構成: パブリックエンドポイント・VNet なし(閉域版は survey architecture 07)"),
        ("実測", (
            "2026-07-31 ライブ: 収集 2,407 → 要約 2,329 → 分析 4,398 字で完走。"
            "2026-09-29 に core 1.19 / openai 3.20 でオフライン再確認"
        )),
    ],
    source="出典: labs/maf-ports/ports/trend-analysis/README.md",
)

d.save(str(_here.parent / "architecture.png"))

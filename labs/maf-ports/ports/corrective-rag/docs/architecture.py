"""corrective-rag(Port 4)のアーキテクチャ図(v2 スタイル: 日本語+処理順バッジ)。

Regenerate(labs/maf-ports で):  uv run --with diagrams,pillow python ports/corrective-rag/docs/architecture.py
"""

import sys
from pathlib import Path

_here = Path(__file__).resolve()
for _p in _here.parents:
    if (_p / "tools" / "archdiagram.py").exists():
        sys.path.insert(0, str(_p / "tools"))
        break
from archdiagram import BLUE, ORANGE, TELEM, Diagram, icon, std_azure

d = Diagram(
    "corrective-rag — 補正ループ RAG + Azure AI Search(Port 4)",
    width=1560,
    height=1010,
    subtitle="検索 → 文書ごとの採点 → 低関連なら 1 回だけクエリ書換+Web 検索 → 生成。"
    "Qdrant を AI Search(Free)に置き換え、埋め込みはクライアント側で行う",
)

# --- ローカル PC ---------------------------------------------------------------
local = d.cluster(40, 100, 730, 655, "ローカル PC(uv + MAF)", kind="local")
wf = d.cluster(180, 145, 710, 470, "MAF ワークフロー(switch-case 分岐)", kind="focus")

cli = d.node(105, 225, icon("cli"), "CLI\ncorrective-rag-maf")
retrieve = d.box(270, 225, 130, 46, "retrieve\n(上位 4 件を取得)")
grade = d.box(445, 225, 158, 46, "grade_documents\n(文書ごとに yes/no)")
generate = d.box(632, 225, 118, 46, "generate\n(回答生成)")
transform = d.box(445, 370, 158, 46, "transform_query\n(クエリ書換)")
websearch = d.box(270, 370, 130, 46, "web_search\n(最大 3 件・3 試行)")
setup = d.box(505, 620, 262, 44, "scripts/setup_index.py\n(索引作成+12 チャンク投入・1 回)")

d.edge(retrieve, grade)
d.edge(grade, generate, label="全件関連", label_dy=-14)
d.edge(grade, transform, label="低関連あり", label_dx=-40, label_dy=0)
d.edge(transform, websearch)
d.edge(websearch.port("bottom", 0.75), generate.port("bottom"), via=[(302.5, 438), (632, 438)],
       label="再採点なし", label_t=0.62, label_dy=-12)

# --- 外部 Web(Azure 外) --------------------------------------------------------
d.cluster(40, 680, 440, 830, "外部 Web(Azure 外)", kind="external")
ddg = d.node(250, 748, icon("browser"), "DuckDuckGo HTML", note="キー不要")

# --- Azure(共有基盤+本ポート固有) ------------------------------------------------
az = std_azure(d, x0=770, y0=100, x1=1520, y1=858, foundry_h=380, ja=True,
               model_note="採点・書換・生成で共用")
model, appi = az["model"], az["appi"]
embed = d.node(1290, 430, icon("model"), "埋め込みデプロイ\ntext-embedding-3-small",
               note="本ポートで追加(1536 次元)", status="GA")
search = d.node(1145, 605, icon("search"), "AI Search(Free)\nsrch-mafports",
                note="インデックス 3 個 / 50 MB", note_color=ORANGE)

# --- 処理の流れ ------------------------------------------------------------------
d.edge(setup.port("right"), (1113, 620), step=0, label="索引・文書", label_t=0.3, label_pos="below")
d.edge(cli, retrieve, step=1, label="質問", label_t=0.45, label_pos="above")
d.edge((710, 430), embed, step=2, label="埋め込み", label_color=BLUE, label_t=0.2,
       label_pos="above")
d.edge((710, 458), (1113, 590), via=[(750, 458), (750, 590)], step=3, label="ベクトル検索",
       label_color=BLUE, label_t=0.62, label_pos="above")
d.edge((710, 310), model, step=4, label="採点・書換・生成", label_color=BLUE, label_t=0.3,
       label_pos="above")
d.edge(websearch.port("bottom", 0.346), ddg, step=5, label="Web 検索", label_t=0.62, label_pos="left")
d.edge(local.port("bottom", 0.93), appi, via=[(682, 750)], style="dashed", color=TELEM,
       label="OTel トレース", label_t=0.6, label_dy=-12)

d.steps_panel(40, 888, 1520, [
    "事前に setup_index.py で 12 チャンクを投入",
    "CLI から質問を受け取り retrieve へ",
    "質問を text-embedding-3-small で埋め込む",
    "AI Search のベクトル検索で上位 4 件を取得",
    "gpt-5.4-mini で採点、書換、回答生成",
    "低関連ありなら書換後のクエリで Web 検索(1 回)",
], numbers=["0", "1", "2", "3", "4", "5"], columns=3)

d.notes(
    [
        ("課金", (
            "AI Search Free は月額 0(1 サブスクリプション 1 つ・インデックス 3 個・50 MB)。"
            "チャットと埋め込みは呼び出しごとのトークン課金"
        )),
        ("制約", "Free のセマンティックランカーは無料枠のみ(従量プランは Basic 以上)。本ポートは純ベクトル検索"),
        ("運用", "2 段デプロイ: main.bicep(AI Search+埋め込みデプロイ)→ setup_index.py(索引と文書は Bicep 外)"),
        ("認証", "チャット・埋め込み = API キー(ラボの .env)/ AI Search = 管理キー(本番は RBAC + Key Vault)"),
        ("閉域", "ラボ構成: パブリックエンドポイント・VNet なし(閉域版は survey architecture 07)"),
    ],
    source="出典: labs/maf-ports/ports/corrective-rag/README.md",
)

d.save(str(_here.parent / "architecture.png"))

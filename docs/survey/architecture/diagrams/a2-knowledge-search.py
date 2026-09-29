"""A2: 全社ナレッジ検索(AI Search 自前索引・04章)のアーキテクチャ図(v2 スタイル: 日本語+処理順バッジ)。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/a2-knowledge-search.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import BLUE, F_LABEL_B, GREEN, INK, MUTED, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "A2: 全社ナレッジ検索 ── AI Search 自前インデックス(本番の標準形)",
    width=1560,
    height=860,
    subtitle="ユーザーごとに見える文書が違う(セキュリティフィルタ / ACL)。チャンク・埋め込み・メタデータは自分で握り、"
    "統合ベクトル化とセマンティックランカーはマネージドのまま使う",
)

ROW = 220  # query row
ING = 470  # ingestion row

# --- 利用者・文書ソース(Azure 外・左) ----------------------------------------------
d.cluster(40, 110, 215, 330, "利用者", kind="external")
user = d.node(128, ROW, res("onprem/client/user.png"), "社員", note="見える文書だけ")
d.cluster(40, 350, 215, 615, "文書ソース", kind="external")
docs = d.node(128, ING, icon("files"), "Blob / SharePoint /\nファイルサーバ", note="数万〜数十万文書")

# --- Azure --------------------------------------------------------------------
d.cluster(240, 100, 1520, 630, "Azure サブスクリプション", kind="azure")
appsvc = d.node(345, ROW, az("appservices/app-services.png"), "App Service", note="グループ ID を解決")

fc = d.cluster(445, 140, 880, 325, "Foundry プロジェクト", kind="sub")
agent = d.node(565, ROW, icon("project"), "Prompt / Hosted\nagent", note="AI Search ツール")
model = d.node(775, ROW, icon("model"), "モデルデプロイ")

d.cluster(260, 350, 880, 615, "取り込みパイプライン(設計は自前)", kind="sub")
cu = d.node(365, ING, az("aimachinelearning/cognitive-services.png"),
            "Content Understanding /\nDocument Intelligence", note="表・見出しを構造化")
indexer = d.box(660, ING, 230, 58, "インデクサ + スキルセット\n(Text Split + 埋め込み)")
d.text(660, ING + 38, "統合ベクトル化・index projections", anchor="ma")

sc = d.cluster(905, 140, 1500, 615, "Azure AI Search(自前インデックス)", kind="focus")
index = d.node(1040, 340, icon("search"), "インデックス", note="チャンク 512 / 重複 25%(公式)")

# 文書単位アクセス制御 4 方式(ステータスは 04 章の表)
d.text(1195, 180, "文書単位のアクセス制御(4 方式)", font=F_LABEL_B, fill=INK)
acl = [
    ("セキュリティフィルタ\nグループ ID をフィールドに入れて絞る", "GA", True),
    ("POSIX 風 ACL / RBAC スコープ\nEntra プリンシパルと権限メタデータを照合", "Preview", False),
    ("Purview 秘密度ラベル\nクエリ時に Purview ポリシーを評価", "Preview", False),
    ("SharePoint ACL\nSharePoint の権限を直接取り込む", "Preview", False),
]
for i, (label, status, ga) in enumerate(acl):
    kw = dict(fill=(236, 248, 240), border=GREEN) if ga else {}
    d.box(1340, 245 + i * 72, 290, 50, label, status=status, **kw)
d.text(1195, 540, "GA 要件を満たせるのはセキュリティフィルタだけ。\nPreview 方式はクエリ時にユーザートークンを\n"
       "x-ms-query-source-authorization で渡す", fill=MUTED)

# --- 処理の流れ(下段) ------------------------------------------------------------
d.steps_panel(40, 652, 1520, [
    "文書を CU / DI で構造化して取り込む",
    "インデクサがチャンク化・埋め込み・権限を投影",
    "社員が Entra ID でサインインして質問",
    "アプリがグループ ID を検索フィルタに反映",
    "agent が Private Endpoint 経由でハイブリッド検索",
    "権限内のチャンクだけを使ってモデルが回答",
], numbers=["A", "B", "1", "2", "3", "4"], columns=3)

# --- edges --------------------------------------------------------------------
d.edge(docs, cu, step="A", label_t=0.39)
d.edge(cu, indexer)
d.edge(indexer, index, via=[(index.cx, ING)], step="B", label_t=0.6)
d.edge(user, appsvc, step=1, label_t=0.44, label="Entra ID", label_color=BLUE, label_pos="above")
d.edge(appsvc, agent, step=2, label_t=0.62)
d.edge((fc.x1, ROW), index, via=[(index.cx, ROW)], step=3, label="PE", label_color=BLUE,
       label_t=0.3, label_pos="above")
d.edge(agent, model, step=4, label_t=0.5)

d.notes(
    [
        ("制約", "チャンク戦略は「準恒久的な選択」(公式)。変えると全件再インデックス → サイズ・重複・日本語アナライザーを先に決める"),
        ("注意", "チャンク分割時は権限フィールドを index projections へ移す(忘れると静かに漏れる)。権限変更は次回インデクサ実行で反映"),
        ("閉域", "インデクサの executionEnvironment を \"Private\" に。未設定だと PE を越えられず、空インデックスのままサイレントに失敗"),
        ("制約", "セマンティックランカーは上位 50 件だけを再ランク(L1 の取りこぼしは救えない)。ベクトル容量はパーティション単位のハード上限"),
        ("認証", "agent → AI Search はマネージド ID + Private Endpoint。ユーザー別の可視性はクエリで強制し、プロンプトでは制御しない"),
    ],
    source="出典: docs/survey/architecture/04 A2(閉域版は 07 章)",
)

d.save(
    str(_here.parent.parent / "images" / "a2-knowledge-search.png"),
    slide=str(_here.parent.parent / "images" / "slide" / "a2-knowledge-search.png"),
)

"""E2: 文書処理・IDP パイプライン(08章)のアーキテクチャ図(v2 スタイル: 日本語+処理順バッジ)。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/e2-idp.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import ORANGE, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "E2: 文書処理・IDP — キュー駆動の取り込みパイプライン + 人手レビュー",
    width=1560,
    height=800,
    subtitle="最初に DI と Content Understanding を選び分ける: 定型帳票 = DI プリビルト / マルチモーダル・RAG 前処理 = CU / "
    "エアギャップ = DI コンテナ(CU はコンテナなし)",
)

# --- 文書投入・レビュー(Azure 外・左) -------------------------------------------
d.cluster(40, 110, 260, 560, "文書投入・レビュー", kind="external")
docs = d.node(150, 230, icon("files"), "Blob / SharePoint /\nメール・スキャナ")
reviewer = d.node(150, 470, res("onprem/client/user.png"), "レビュー担当者")

# --- Azure --------------------------------------------------------------------
d.cluster(285, 100, 1325, 640, "Azure サブスクリプション", kind="azure")
queue = d.node(370, 230, az("integration/service-bus.png"), "Service Bus /\nQueue Storage", note="再試行の受け皿")

d.cluster(455, 140, 880, 545, "処理ワーカー", kind="focus", sublabel="Durable Functions / Container Apps jobs 等")
extract = d.box(560, 230, 124, 40, "構造抽出")
judge = d.box(560, 350, 124, 40, "信頼度判定")
review = d.box(560, 470, 124, 40, "人手レビュー",
               fill=(255, 248, 230), border=(196, 140, 40))
chunk = d.box(775, 350, 140, 48, "チャンク分割\n+ 埋め込み")
index = d.box(775, 470, 124, 40, "索引・保存")
d.edge(queue, extract)
d.edge(extract, judge)
d.edge(judge, chunk, label="高", label_t=0.5, label_dy=-11)
d.edge(judge, review, label="低", label_t=0.5, label_dx=-14, label_dy=0)
d.edge(review, index, label="修正後", label_t=0.5, label_dy=-11)
d.edge(chunk, index)

# 右列: Foundry Tools / モデル / ストア
dicu = d.node(1000, 230, az("aimachinelearning/form-recognizers.png"),
              "Document Intelligence /\nContent Understanding", status="GA")
batch = d.node(1000, 350, icon("model"), "埋め込み(Batch)", status="GA",
               note="Global Standard 比 50% 割引", note_color=ORANGE)
search = d.node(1000, 470, icon("search"), "AI Search インデックス")
cosmos = d.node(1000, 578, az("databases/azure-cosmos-db.png"), "Cosmos DB(メタデータ)", icon_size=48)
models = d.node(1210, 230, icon("model"), "LLM・埋め込み\nデプロイ", note="CU は持ち込み必須")
agent = d.node(1210, 470, icon("foundry"), "Foundry\nエージェント")

# --- 利用者(Azure 外・右) -------------------------------------------------------
d.cluster(1350, 110, 1520, 560, "利用者", kind="external")
user = d.node(1435, 470, res("onprem/client/users.png"), "業務ユーザー")

# --- edges --------------------------------------------------------------------
d.edge(docs, queue, step=1, label_t=0.5)
d.edge(extract, dicu, step=2, label="解析", label_t=0.62, label_pos="above")
d.edge(dicu, models, label="BYO", label_t=0.5, label_dy=-11)
d.edge(review.port("left"), reviewer, both=True, step=3, label="確認・修正", label_t=0.5, label_pos="below")
d.edge(chunk, batch, step=4, label_t=0.6)
d.edge(index, search, step=5, label_t=0.55)
d.edge(index.port("bottom"), cosmos, via=[(775, 578)])
d.edge(agent, search, step=6, label="検索", label_t=0.45, label_pos="above")
d.edge(agent, models, label="推論", label_t=0.5, label_dx=22, label_dy=0)
d.edge(user, agent, label="質問", label_t=0.5, label_dy=-11)

d.steps_panel(40, 668, 1520, [
    "文書をキューに投入(再試行はキュー側)",
    "DI / CU でレイアウト・フィールドを抽出",
    "低信頼度の結果は人手レビューへ回す",
    "チャンク分割し Batch デプロイで埋め込み",
    "AI Search に索引、メタデータは Cosmos DB",
    "エージェントが索引を検索して回答",
], columns=3)

d.notes(
    [
        ("制約", "ページ上限が逆転: CU は 300 ページ、DI Layout は 2,000 ページ → 超長尺 PDF は上流で分割するか DI を選ぶ"),
        ("注意", "CU は GA でマネージドモデル容量が廃止 → LLM・埋め込みデプロイを持ち込む(例外は prebuilt-read / -layout のみ)"),
        ("課金", "AI Search のスキル経由はレイアウト処理 5 分超でタイムアウトしても課金。CU スキルは無料枠なし"),
        ("注意", "DI v4 の Markdown 出力は表を HTML テーブルで返す(パイプ表ではない)→ 後段パーサを合わせる"),
        ("閉域", "エアギャップは DI コンテナ(構造化抽出)/ Vision Read コンテナ(OCR)。CU はコンテナなし(07章 9.3)"),
    ],
    source="出典: docs/survey/architecture/08 E2",
)

d.save(
    str(_here.parent.parent / "images" / "e2-idp.png"),
    slide=str(_here.parent.parent / "images" / "slide" / "e2-idp.png"),
)

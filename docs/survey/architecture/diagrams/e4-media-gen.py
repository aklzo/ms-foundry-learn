"""E4: マルチモーダル生成(画像・動画、08章)のフロー図(v2 スタイル: 日本語+処理順バッジ)。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/e4-media-gen.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import ORANGE, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "E4: 画像・動画生成 — キューによる負荷平準化が実質必須",
    width=1540,
    height=800,
    subtitle="画像は 6〜36 RPM、Sora 2 は 2 job RPM + 同時 2 ジョブ + 24h 失効。Azure Architecture Center に"
    "メディア生成の公式パターンはなく、Queue-Based Load Leveling / Competing Consumers を当てる",
)

Y = 330  # 主軸

# --- 利用者(Azure 外・左) -------------------------------------------------------
d.cluster(40, 180, 230, 480, "利用者", kind="external")
users = d.node(135, Y, res("onprem/client/users.png"), "業務アプリ /\n利用者")

# --- Azure --------------------------------------------------------------------
d.cluster(255, 100, 1500, 600, "Azure サブスクリプション", kind="azure")
api = d.node(340, Y, az("appservices/app-services.png"), "API", note="ジョブ ID を即時返却")

d.cluster(420, 140, 780, 565, "負荷平準化(キュー + ワーカー)", kind="focus")
queue = d.node(505, Y, az("storage/queues-storage.png"), "Service Bus /\nQueue Storage")
worker = d.node(690, Y, icon("containerapp"), "生成ワーカー", note="RPM 上限でレート制御")
state = d.node(690, 492, az("databases/azure-cosmos-db.png"), "ジョブ状態", note="Cosmos DB", icon_size=48)

d.cluster(830, 140, 1130, 565, "Foundry(モデルデプロイ)", kind="sub")
img = d.node(980, 230, icon("model"), "画像: gpt-image-2 / 2.5・\nFLUX.2(同期 API)", status="GA",
             note="RPM のみ・Data Zone は 1/3", note_color=ORANGE)
vid = d.node(980, 445, icon("model"), "動画: Sora 2\n(非同期ジョブ)", status="Preview",
             note="2 job RPM・同時 2・24h 失効", note_color=ORANGE)
d.pill(vid.x1 - 6 + 56, vid.y0 + 2, "廃止予定")  # sora-2: 2026-10-15 リタイア・後継未掲載

blob = d.node(1265, Y, az("storage/blob-storage.png"), "自社 Blob", note="成功後すぐ退避")
review = d.box(1415, Y, 150, 48, "Content Safety\n+ 人手レビュー", fill=(255, 248, 230), border=(196, 140, 40))
pub = d.box(1415, 470, 150, 44, "公開ストレージ\nへ昇格")

# --- edges --------------------------------------------------------------------
d.edge(users, api, step=1, label_t=0.5)
d.edge(api, queue)
d.edge(queue, worker, step=2, label_t=0.5)
d.edge(worker, state, label="保存", label_t=0.5, label_dx=20, label_dy=0)
# ワーカーから画像 / 動画へ分岐
d.edge((722, Y), img, via=[(805, Y), (805, 230)], step=3, label="生成", label_t=0.86, label_pos="above")
d.edge((722, Y), vid, via=[(805, Y), (805, 445)], step=4, label="作成・ポーリング", label_t=0.86,
       label_pos="below")
# 画像 / 動画から Blob へ合流
d.edge(vid, blob, via=[(1165, 445), (1165, Y)])
d.edge(img, blob, via=[(1165, 230), (1165, Y)], step=5, label="24h 以内", label_t=0.88,
       label_pos="above", label_color=ORANGE)
d.edge(blob, review, step=6, label_t=0.45)
d.edge(review, pub, label="承認", label_t=0.5, label_dx=20, label_dy=0)

d.steps_panel(40, 628, 1500, [
    "要求を受けたらジョブ ID を即時返却",
    "キューで平準化し RPM 上限内で取り出す",
    "画像は同期 API。429 は指数バックオフ",
    "動画はジョブ作成 → 状態を保存しポーリング",
    "成功したら 24h 以内に自社 Blob へ退避",
    "Content Safety・人手レビュー後に公開",
], columns=3)

d.notes(
    [
        ("期限", "sora-2 は 2026-10-15 リタイアで後継未掲載 → 動画生成を長期案件の前提に置かない(gpt-image-1 は 10-23 リタイア)"),
        ("制約", "画像は TPM なし RPM のみ(gpt-image-2: Tier1 6〜Tier6 36)。Data Zone は Global の約 1/3、2.5 系は全 Tier 5 RPM 固定"),
        ("制約", "Sora 2 のジョブは作成後 24h で失効し、自社 Blob への直接出力(BYO)は記載なし → 成功後すぐ退避する"),
        ("注意", "Sora 2 は IP・フォトリアル・実在人物・顔入り入力画像を拒否 → 企画段階で用途が成立するか先に確認"),
        ("注意", "画像は C2PA・透かしを自動付与(gpt-image-1・2.5 系は対応表になし)。動画は対象外 → 自前付与を検討"),
    ],
    source="出典: docs/survey/architecture/08 E4",
)

d.save(
    str(_here.parent.parent / "images" / "e4-media-gen.png"),
    slide=str(_here.parent.parent / "images" / "slide" / "e4-media-gen.png"),
)

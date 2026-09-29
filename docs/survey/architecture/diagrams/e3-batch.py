"""E3: 大量バッチ処理(08章)のフロー図(v2 スタイル: 日本語+処理順バッジ)。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/e3-batch.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import F_LABEL_B, FOCUS_FILL, INK, ORANGE, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "E3: 大量バッチ処理 — リアルタイムでなくてよい処理を Batch に切り出す",
    width=1460,
    height=780,
    subtitle="Batch デプロイは Global Standard 比 50% 割引。クォータプールがオンラインと分離しているので、"
    "日中のチャットと夜間の一括処理を同じリソースに同居させられる",
)

# --- 入力(Azure 外・左) ----------------------------------------------------------
d.cluster(40, 110, 250, 560, "入力", kind="external")
src = d.node(145, 230, az("storage/blob-storage.png"), "Blob / DB /\nイベント", note="夜間の一括対象")
chat = d.node(145, 445, res("onprem/client/users.png"), "チャット利用者", note="日中の対話")

# --- Azure --------------------------------------------------------------------
d.cluster(275, 100, 1420, 580, "Azure サブスクリプション", kind="azure")
job = d.node(375, 230, az("compute/function-apps.png"), "ジョブ生成(JSONL)", note="Functions / CA jobs")

fr = d.cluster(470, 140, 850, 545, "Foundry リソース", kind="focus")
batch = d.node(660, 230, icon("model"), "Batch デプロイ", status="GA",
               note="enqueued tokens クォータ", note_color=ORANGE)
online = d.node(660, 445, icon("model"), "オンライン デプロイ", status="GA",
                note="TPM クォータ(Global Standard 等)", note_color=ORANGE)
# クォータ分離の仕切り線
d._dashed_line((482, 342), (838, 342), (150, 160, 175), 2)
d._text_block((660, 342), ["クォータプールは完全に分離"], F_LABEL_B, INK, anchor="mm", bg=FOCUS_FILL)

result = d.node(1000, 230, az("storage/blob-storage.png"), "結果 JSONL", note="BYO Blob 可")
post = d.node(1290, 230, az("compute/container-apps.png"), "取り込み・後処理")

levers = d.cluster(890, 385, 1400, 545, "併用できるコストレバー", kind="sub")
d.box(975, 478, 145, 48, "Model router\n(Cost モード)", status="GA")
d.box(1145, 478, 145, 48, "小型モデル\n(品質検証が前提)")
d.box(1315, 478, 145, 48, "Prompt caching\n(先頭 1,024 トークン)")

# --- edges --------------------------------------------------------------------
d.edge(src, job, step=1, label_t=0.5)
# 投入(上)と即時エラー時の再投入(下)を平行線で
d.edge((407, 218), (628, 218), step=2, label="投入", label_t=0.5, label_pos="above")
d.edge((628, 246), (407, 246), step=3, label="容量超過", label_t=0.5, label_pos="below", color=ORANGE,
       label_color=ORANGE)
d.edge(batch, result, step=4, label="24h 目標", label_t=0.72, label_pos="above")
d.edge(result, post, step=5, label_t=0.5)
d.edge(chat, online, label="リアルタイム", label_t=0.3, label_dy=-11)

d.steps_panel(40, 606, 1420, [
    "投入データから JSONL を生成(10 万件/ファイル)",
    "Batch デプロイへ投入(completion_window=24h)",
    "容量超過は即時エラー → 指数バックオフで再投入",
    "24h 目標で処理し結果 JSONL を出力",
    "結果を取り込み、後段の業務処理へ反映",
], columns=3)

d.notes(
    [
        ("課金", "Batch は Global Standard 比 50% 割引。「リアルタイムでなくてよい処理」を PoC 段階で切り出して設計に入れる"),
        ("制約", "completion_window は \"24h\" 固定(他の値はジョブ失敗)/ 1 ファイル 10 万リクエスト / 入力 200MB(BYO Blob なら 1GB)"),
        ("運用", "Dynamic quota を ON にして余剰容量を機会的に使う。24h を超えてもジョブは失効せず実行を継続する"),
        ("推奨", "バッチが暴走してもオンライン側のクォータを食わない → 「日中はチャット、夜間は一括」を同一リソースに同居"),
        ("注意", "Model router の Cost モードは有効コンテキストが最小の下位モデルに制限 → 大きな入力は model subset で絞る"),
    ],
    source="出典: docs/survey/architecture/08 E3",
)

d.save(
    str(_here.parent.parent / "images" / "e3-batch.png"),
    slide=str(_here.parent.parent / "images" / "slide" / "e3-batch.png"),
)

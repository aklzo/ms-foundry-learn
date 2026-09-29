"""E6: ファインチューニング運用(08章)。処理フロー(MLOps ループ)として描く(v2 スタイル: 日本語+処理順バッジ)。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/e6-finetune-ops.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import F_LABEL_B, MUTED, ORANGE, RED, Diagram, az, icon  # noqa: E402

d = Diagram(
    "E6: ファインチューニング運用 — 作って終わりではなく回し続けるループ",
    width=1500,
    height=800,
    subtitle="多くのユースケースで FT は不要(まず RAG でグラウンディング)。必要なら SFT → DPO を serverless で学習し、"
    "評価は Developer tier、ベースモデルのリタイアに合わせて再学習する",
)

YT, YB = 230, 460  # ループの上段 / 下段

# --- 学習データ(左) -------------------------------------------------------------
d.cluster(40, 110, 225, 560, "学習データ", kind="external")
data = d.node(132, YT, az("storage/storage-accounts.png"), "JSONL\n(プロンプト・応答)", note="本番は 500 件以上")

# --- Azure --------------------------------------------------------------------
d.cluster(250, 100, 1475, 590, "Azure サブスクリプション", kind="azure")
d.cluster(275, 140, 1115, 560, "MLOps ループ(既存の MLOps 投資を流用)", kind="focus")

ft = d.node(380, YT, az("aimachinelearning/azure-applied-ai-services.png"), "ファインチューニング\n(SFT → DPO / RFT)",
            status="GA", note="serverless が最良のバランス")
model = d.box(585, YT, 132, 48, "カスタムモデル\n(保管は無料)")
dev = d.node(790, YT, icon("model"), "Developer tier\n(評価用デプロイ)", status="GA",
             note="時間料金なし・SLA なし", note_color=ORANGE)
ev = d.node(1005, YT, icon("evals"), "評価\n(評価 SDK)", note="品質ゲート")

mon = d.node(790, YB, icon("appinsights"), "監視 + キープアライブ", note="レイテンシ・トークン・429")
retire = d.box(545, YB, 180, 52, "ベースモデルの\nリタイア通知", fill=(255, 240, 238), border=(200, 90, 90))

# ループ中央の一言
d.text(695, 345, "ベースモデルは 12〜18 か月でリタイア → 定期的な再学習を予算化", fill=MUTED, anchor="mm")

# --- 本番デプロイ種別(右) --------------------------------------------------------
prod = d.cluster(1140, 140, 1455, 560, "本番デプロイ", kind="sub", sublabel="時間課金・15 日無通信で削除")
d.box(1297, 250, 240, 46, "Standard(リージョン)", status="GA")
d.box(1297, 345, 240, 46, "Global Standard\n(重みが地理外に出うる)", status="Preview")
d.box(1297, 440, 240, 46, "Provisioned(PTU)", status="Preview")
d.text(1297, 505, "ゲートウェイ経由で段階展開・No Auto Upgrade", anchor="ma")

# --- edges --------------------------------------------------------------------
d.edge(data, ft, step=1, label_t=0.5)
d.edge(ft, model, step=2, label_t=0.5)
d.edge(model, dev, step=3, label_t=0.5)
d.edge(dev, ev, label="24h で自動削除", label_color=ORANGE, label_t=0.5, label_dy=-12)
d.edge(ev, (1140, YT), step=4, label="合格", label_t=0.4, label_pos="above")
d.edge((1140, YB), mon, step=5, label_t=0.35)
d.edge(mon, retire, label="通知", label_t=0.5, label_dy=-12)
d.edge(retire, ft, via=[(380, YB)], step=6, label="新ベースで再学習", label_t=0.7, label_pos="right")

d.steps_panel(40, 612, 1475, [
    "JSONL の学習データを用意(本番は 500 件〜)",
    "SFT → DPO の順で学習(serverless 推奨)",
    "Developer tier にデプロイして評価",
    "品質ゲート通過後に本番へ段階展開",
    "監視 + キープアライブ(15 日無通信で削除)",
    "ベースのリタイア前に新ベースで再学習",
], columns=3)

d.notes(
    [
        ("課金", "FT デプロイは呼び出しの有無に関わらず時間課金(保管は無料)→「デプロイ数 × 稼働時間」が固定費。使わないデプロイは消す"),
        ("運用", "15 日を超えて非アクティブなデプロイは削除される(モデル本体は残る)→ キープアライブか再デプロイ手順を用意"),
        ("期限", "2 段階リタイア: training 停止の約 6 か月後に deployment 停止(例: gpt-4.1 系は 2027-10-14)。リタイア日は延長不可"),
        ("注意", "Global Standard はカスタム重みが地理的範囲外に保存されうる → 規制案件は Standard(リージョン)を選ぶ"),
        ("閉域", "Blob からの学習データ取り込みはストレージのパブリックアクセスが必要 → 閉域ではローカル / SDK からアップロード"),
    ],
    source="出典: docs/survey/architecture/08 E6",
)

d.save(
    str(_here.parent.parent / "images" / "e6-finetune-ops.png"),
    slide=str(_here.parent.parent / "images" / "slide" / "e6-finetune-ops.png"),
)

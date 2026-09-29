"""D3: エッジ・オンプレ 3 形態(07章 §9)の比較図(v2 スタイル: 日本語+処理順バッジ)。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/d3-edge-onprem.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import F_CLUSTER, RED, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "D3: エッジ・オンプレ — 名前が似た 3 つの別物",
    width=1560,
    height=800,
    subtitle="端末上の SDK(GA)/ オンプレ K8s の推論基盤(プレビュー・申請制)/ エアギャップの Foundry Tools "
    "コンテナ(サービスごとに GA / プレビュー)を最初に切り分ける",
)

WARN_FILL = (255, 241, 240)
WARN_BORDER = (207, 34, 46)


def header_pill(x0: float, y0: float, label: str, status: str, extra: str | None = None) -> None:
    """Status pill (+ optional grey remark) right after a cluster label (clusters have no status)."""
    p = d.pill(x0 + 12 + d.d.textlength(label, font=F_CLUSTER) + 10, y0 + 17, status)
    if extra:
        d.text(p.x1 + 6, y0 + 10, extra)


# --- ① 端末上: Foundry Local ------------------------------------------------------------
L1 = "利用者の端末 — Foundry Local"
d.cluster(40, 110, 520, 620, L1, kind="local")
header_pill(40, 110, L1, "GA")
app1 = d.node(280, 200, icon("cli"), "アプリ + SDK", note="インプロセス推論・追加約 20MB")
rt = d.box(280, 350, 330, 40, "ONNX Runtime(GPU / NPU を自動選択)")
mdl = d.box(280, 450, 380, 50, "チャット(GPT-OSS / Qwen / DeepSeek / Mistral / Phi)\n+ 音声書き起こし(Whisper)のみ")
d.box(280, 555, 300, 50, "サーバー用途は公式に否定\n(同時ユーザー → vLLM 等を使う)", fill=WARN_FILL,
      border=WARN_BORDER, text_color=RED)

# --- ② オンプレ K8s: Foundry Local on Azure Local ---------------------------------------
L2 = "オンプレ K8s — Foundry Local on Azure Local"
d.cluster(540, 110, 1020, 620, L2, kind="local")
header_pill(540, 110, L2, "Preview", "申請制")
clients = d.node(780, 200, res("onprem/client/users.png"), "社内の利用者 / アプリ", note="複数ユーザー")
gw = d.box(780, 350, 340, 50, "Gateway API(Istio)\n認証: キー / Entra / K8s SAT(2609)")
eng = d.box(780, 450, 340, 40, "ONNX-GenAI(CPU / GPU)or vLLM(GPU)")
op = d.node(780, 540, az("other/arc-kubernetes.png"), "Arc 拡張(inference operator)",
            note="Model / ModelDeployment CRD", icon_size=52)

# --- ③ エアギャップ: 切断コンテナ -----------------------------------------------------------
L3 = "エアギャップ — 切断コンテナ"
d.cluster(1040, 110, 1520, 620, L3, kind="local", sublabel="申請制・サービスごと")
app3 = d.node(1180, 200, icon("cli"), "閉域の業務アプリ", note="インターネット接続ゼロ")
di = d.node(1180, 370, icon("container"), "Document Intelligence", note="構造化抽出の唯一の選択肢",
            status="GA")
oth = d.box(1405, 370, 190, 64, "Vision Read OCR / Speech\n/ Language / Translator\n(一部プレビュー)")
d.box(1280, 540, 360, 50, "Content Understanding はコンテナなし\n→ マルチモーダル文書処理はオンプレ不可", fill=WARN_FILL,
      border=WARN_BORDER, text_color=RED)

# --- 処理の流れ(下段) ----------------------------------------------------------------
d.steps_panel(40, 650, 1520, [
    "端末内のアプリに埋め込んで推論(Foundry Local)",
    "社内の複数ユーザーへ推論 API を提供(Azure Local)",
    "接続ゼロの環境で文書・音声を処理(切断コンテナ)",
], columns=3, title="使い分け(処理の流れ)")

# --- edges ------------------------------------------------------------------------
d.edge(app1, rt, step=1, label_t=0.5)
d.edge(rt, mdl)
d.edge(clients, gw, step=2, label_t=0.5)
d.edge(gw, eng)
d.edge(op, eng, label="CRD で調停", label_t=0.5, label_dx=52, label_dy=0)
d.edge(app3, di, step=3, label_t=0.5)
d.edge(app3, oth, via=[(1405, 200)])

d.notes(
    [
        ("制約", "Foundry Local は埋め込み・ビジョンモデルなし。サーバー推論(バッチング・GPU 共有)は提供しないと明記 → 同時ユーザーは vLLM 等"),
        ("運用", "Azure Local 版は 18 リージョン(Japan East 含む)。拡張 2609 で拡張 MI に Arc K8s の Reader が必須。既定ワーカーは「通常小さすぎる」"),
        ("課金", "切断コンテナは申請(10 営業日以内)・承認サブスクリプションのみ。コミットメントは暦年単位で購入時に全額課金"),
        ("注意", "Content Safety / Fast transcription の切断対応はページ間で不整合 → エアギャップ案件は事前に確認"),
        ("制約", "クラウド + エッジのハイブリッドに公式ガイダンスなし。オフラインではエージェント・ガードレール・観測性は使えない"),
    ],
    source="出典: docs/survey/architecture/07 §9",
)

d.save(
    str(_here.parent.parent / "images" / "d3-edge-onprem.png"),
    slide=str(_here.parent.parent / "images" / "slide" / "d3-edge-onprem.png"),
)

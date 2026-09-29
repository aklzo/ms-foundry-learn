"""critique-loop(Port 9)のアーキテクチャ図(v2 スタイル: 日本語+処理順バッジ)。

Regenerate(labs/maf-ports で):
    uv run --with diagrams,pillow python ports/critique-loop/docs/architecture.py
"""

import sys
from pathlib import Path

_here = Path(__file__).resolve()
_tools = next(p / "tools" for p in _here.parents if (p / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_tools))

from archdiagram import BLUE, MUTED, ORANGE, TELEM, Diagram, icon, std_azure

d = Diagram(
    "critique-loop — 批評・改善ループ + クラウド評価(Port 9)",
    width=1500,
    height=1000,
    subtitle="実行時の critic は制御信号(リクエストパス内)、クラウド評価は測定(非同期ジョブ)。"
    "上限打ち切りで実行時には誰も批評しない最終版もクラウド評価が採点する",
)

# --- ローカル(uv + MAF) -----------------------------------------------------------
local = d.cluster(40, 100, 870, 640, "ローカル PC(uv + MAF)", kind="local")
wf = d.cluster(190, 140, 850, 520, "MAF ワークフロー(fan-out / fan-in + ループエッジ)", kind="focus")

cli = d.node(110, 250, icon("cli"), "CLI\ncritique-loop-maf")
disp = d.box(290, 250, 110, 44, "dispatcher")
cands = [
    d.box(470, 190, 180, 36, "候補: structured"),
    d.box(470, 250, 180, 36, "候補: practical"),
    d.box(470, 310, 180, 36, "候補: skeptical"),
]
synth = d.box(690, 250, 140, 48, "synthesize\n(fan-in で統合)")
critic = d.box(690, 385, 160, 48, "critic\n(verdict + 批評)")
revise = d.box(450, 385, 130, 44, "revise(改訂)")
final = d.box(690, 475, 130, 38, "finalize")
d.text(
    215, 430,
    "上限 --max-rounds 1〜3(既定 2)\n上限到達時の critic は LLM を呼ばずに打ち切り",
    fill=MUTED,
)
script = d.box(520, 592, 640, 40, "scripts/run_cloud_eval.py runs/*.json(保存した版列を evals API へ提出)")

# --- Azure(共有基盤のみ。ポート固有リソースなし) --------------------------------------
shared = std_azure(
    d, x0=900, y0=100, x1=1460, y1=740, base="mafportsw2", foundry_h=400, ja=True,
    model_note="ループ 4 役 + 評価の判定モデル",
)
evals = d.node(shared["model"].cx, 482, icon("evals"), "クラウド評価(evals API)", icon_size=56,
               note="coherence・fluency・rubric", status="GA")
d.text(shared["project"].cx, 440, "評価グループ / ランは\nデータプレーンの\nオブジェクト(ARM 型なし)",
       fill=MUTED, anchor="ma")

# --- ワークフロー内の辺 ----------------------------------------------------------------
for c in cands:
    d.edge(disp, c)
    d.edge(c, synth)
d.edge(synth, critic)
d.edge(critic.port("left", 0.3), revise.port("right", 0.3), step=3, label="revise", label_t=0.5,
       label_pos="above")
d.edge(revise.port("right", 0.75), critic.port("left", 0.75), label="改訂版", label_t=0.5, label_dy=14)
d.edge(critic, final, label="accept / 上限", label_t=0.5, label_dx=52, label_dy=0)

# --- 主な流れ ----------------------------------------------------------------------
d.edge(cli, disp, step=1)
d.edge(wf.port("right", (shared["model"].cy - 140) / 380), shared["model"], step=2,
       label="api-key", label_color=BLUE, label_t=0.78, label_pos="above")
d.edge(final.port("bottom"), (final.cx, script.y0), step=4, label="--save-run", label_t=0.62,
       label_pos="right")
d.edge(script.port("right"), (evals.cx - 30, evals.cy), via=[(885, script.cy), (885, evals.cy)],
       step=5, label="Entra ID", label_color=BLUE, label_t=0.8, label_pos="above")
d.edge(evals, shared["model"], step=6, label="判定(課金)", label_color=ORANGE, label_t=0.5,
       label_pos="right")
d.edge(local.port("right", (shared["appi"].cy - 100) / 540), shared["appi"], style="dashed",
       color=TELEM, label="OTel トレース", label_t=0.5, label_dy=-12)

# --- 処理の流れ(下段) ----------------------------------------------------------------
d.steps_panel(40, 768, 1460, [
    "CLI のプロンプトを dispatcher が 3 候補へ配る",
    "候補 3 体を並列生成し 1 本に統合(モデル)",
    "critic が revise なら改訂して再批評(ループ)",
    "accept か上限で終了し --save-run で版列を保存",
    "版列を evals API へ提出(Entra ID のみ)",
    "判定モデルが版ごとに採点 → スコア表",
], columns=3)

d.notes(
    [
        ("実測", ("2026-07-31: 実行時は revise が続いたのに、評価では coherence 4→5・fluency 5→4 — "
                  "制御信号と測定は別物")),
        ("課金", ("判定は自分のデプロイに課金(builtin は initialization_parameters.deployment_name 必須)。"
                  "1 ラン = 版数 × 評価器 3")),
        ("認証", ("ループは api-key / 評価は Entra ID のみ(get_openai_client の bearer)。"
                  "提出ユーザーにも Foundry User が必要")),
        ("運用", ("インフラは共有基盤のみ(main.bicep は既存参照と出力だけ)。評価の経路は "
                  "azure-ai-projects 2.7 + openai 3.20 でも不変")),
        ("注意", "ラボ構成: パブリックエンドポイント・VNet なし(閉域版は survey architecture 07)"),
    ],
    source="出典: labs/maf-ports/ports/critique-loop/README.md",
)

d.save(str(_here.parent / "architecture.png"))

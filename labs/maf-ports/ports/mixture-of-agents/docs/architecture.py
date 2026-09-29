"""mixture-of-agents(Port 2)のアーキテクチャ図(v2 スタイル: 日本語+処理順バッジ)。

Regenerate:  uv run --with diagrams,pillow python ports/mixture-of-agents/docs/architecture.py
"""

import sys
from pathlib import Path

_here = Path(__file__).resolve()
_tools = next(p / "tools" for p in _here.parents if (p / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_tools))
from archdiagram import BLUE, MUTED, TELEM, Diagram, icon, std_azure

d = Diagram(
    "mixture-of-agents — ファンアウト / ファンイン(Port 2)",
    width=1500,
    height=860,
    subtitle="同じ質問を proposer 4 体へ並列に配り、全員の回答を待って aggregator が統合する"
    "(add_fan_out_edges / add_fan_in_edges、agent-framework-core 1.19)",
)

# --- ローカル端末(MAF ワークフロー) ---------------------------------------------
local = d.cluster(40, 100, 770, 630, "ローカル端末(uv + MAF)", kind="local")
wf = d.cluster(200, 150, 750, 610, "MAF ワークフロー(fan-out → fan-in)", kind="focus")

cy = 362
cli = d.node(115, cy, icon("cli"), "CLI", note="mixture-of-agents-maf")
disp = d.box(280, cy, 120, 50, "dispatcher\n入口の正規化")
names = ("analyst", "creative", "skeptic", "pragmatist")
props = [d.box(482, 235 + 85 * i, 160, 40, f"proposer: {n}") for i, n in enumerate(names)]
agg = d.box(675, cy, 112, 56, "aggregator\n(統合)")
bus_out, bus_in = 371, 590  # fan-out / fan-in の縦バス
for i, p in enumerate(props):
    d.edge(disp.port("right"), p, via=[(bus_out, cy), (bus_out, p.cy)],
           step=2 if i == 0 else None, label_t=0.5)
    d.edge(p.port("right"), agg, via=[(bus_in, p.cy), (bus_in, cy)],
           step=3 if i == len(props) - 1 else None, label_t=0.5)
d.text(482, 528, "並列実行・合流の並びはエッジ定義順(決定的)", anchor="ma")
d.text(482, 552, "既定: 1 モデル × ペルソナ 4 体(self-MoA)", anchor="ma")

# --- Azure(共有基盤) ------------------------------------------------------------
shared = std_azure(d, x0=800, y0=100, x1=1460, y1=630, foundry_h=300, ja=True)
model, appi = shared["model"], shared["appi"]
extra = d.box(model.cx, 392, 230, 38, "追加モデルデプロイ(任意)", fill=(250, 250, 250),
              border=(170, 170, 170))
d.text(model.cx, 418, "FOUNDRY_PROPOSER_MODELS で指定", anchor="ma")


def wf_right(y: float) -> tuple[float, float]:
    return wf.port("right", (y - wf.y0) / (wf.y1 - wf.y0))


# --- 処理の流れ ----------------------------------------------------------------------
d.edge(cli, disp, step=1, label_t=0.5)
d.edge(wf_right(model.cy), model, step=4, label="推論 ×5(api-key)", label_color=BLUE,
       label_t=0.33, label_pos="above")
d.edge(wf_right(extra.cy), extra, color=MUTED)
d.edge(local.port("right", 0.97), appi, via=[(785, local.port("right", 0.97)[1]), (785, appi.cy)],
       style="dashed", color=TELEM, step=5, label="OTel", label_color=TELEM, label_t=0.85,
       label_pos="above")

d.steps_panel(40, 660, 1460, [
    "CLI の質問を dispatcher が受けて正規化",
    "fan-out: 4 体へ同じ質問を並列に配送",
    "fan-in: 全員の完了を待ち 1 回だけ集約",
    "proposer 4 + aggregator 1 = 呼び出し 5 回",
    "fan-out / fan-in の配送もスパンとして送信",
], columns=3)

d.notes(
    [
        ("課金", (
            "1 回 = モデル呼び出し 5 回(aggregator の入力が最大)。"
            "モデル多様性モードは追加デプロイごとに容量・課金単位が増える"
        )),
        ("制約", (
            "gpt-5 系は temperature 非対応 → 多様性はペルソナ差で作る。"
            "proposer が 1 体でも失敗すると全体が失敗(部分集約はしない)"
        )),
        ("認証", "モデル = api-key(lab の .env)/ トレース = App Insights 接続文字列"),
        ("閉域", "ラボ構成: 共有基盤のみ・パブリックエンドポイント・VNet なし(閉域版は survey architecture 07)"),
        ("実測", (
            "2026-07-31 ライブ: 4 体並列(1,287〜2,724 字)→ 統合、invoke_agent ×5 着信。"
            "2026-09-29 に core 1.19 / openai 3.20 でオフライン再確認"
        )),
    ],
    source="出典: labs/maf-ports/ports/mixture-of-agents/README.md",
)

d.save(str(_here.parent / "architecture.png"))

"""game-design-team(Port 7)のアーキテクチャ図(v2 スタイル: 日本語+処理順バッジ)。

Regenerate(labs/maf-ports で):  uv run --with diagrams,pillow python ports/game-design-team/docs/architecture.py
"""

import sys
from pathlib import Path

_here = Path(__file__).resolve()
for _p in _here.parents:
    if (_p / "tools" / "archdiagram.py").exists():
        sys.path.insert(0, str(_p / "tools"))
        break
from archdiagram import BLUE, MUTED, NOTE_SHARED_ONLY_JA, TELEM, Diagram, icon, std_azure

d = Diagram(
    "game-design-team — 決定的なリングを 2 周(Port 7)",
    width=1500,
    height=820,
    subtitle="AG2 Swarm の AfterWork リング → 明示グラフのエッジ。1 周目は要約、2 周目は「## X Design」"
    "セクションを GameDesignContext(型付きメッセージ)に書き足す",
)

# --- ローカル PC ---------------------------------------------------------------
local = d.cluster(40, 100, 800, 600, "ローカル PC(uv + MAF)", kind="local")
wf = d.cluster(190, 145, 780, 505, "MAF ワークフロー(リング+ループエッジ)", kind="focus")

cli = d.node(112, 250, icon("cli"), "CLI\ngame-design-team-maf")
story = d.box(290, 250, 100, 44, "story")
gameplay = d.box(432, 250, 100, 44, "gameplay")
visuals = d.box(574, 250, 100, 44, "visuals")
tech = d.box(712, 250, 90, 44, "tech")
deliver = d.box(485, 440, 210, 50, "deliver\n(GameDesignDocument)")
d.text(485, 352, "役割ペルソナ = 静的 instructions / フェーズ指示(要約 or 詳細)は\n"
       "毎ターン prompts.py が組み立てる(UPDATE_SYSTEM_MESSAGE 不要)", fill=MUTED, anchor="ma")

d.edge(gameplay, visuals)
d.edge(visuals, tech)

variant = d.box(420, 552, 390, 46, "比較用: HandoffBuilder 変種(examples/・live 専用)\n"
                "agent-framework-orchestrations 1.2.0")

# --- Azure(共有基盤のみ) ----------------------------------------------------------
az = std_azure(d, x0=830, y0=100, x1=1460, y1=600, foundry_h=260, ja=True, model_note="4 役割で共用")
model, appi = az["model"], az["appi"]

# --- 処理の流れ ------------------------------------------------------------------
d.edge(cli, story, step=1, label="タスク文", label_t=0.45, label_pos="above")
d.edge((780, 259), model, step=2, label="推論 ×8", label_color=BLUE, label_t=0.3, label_pos="above")
d.edge(story, gameplay, step=3, label_t=0.5)
d.edge(tech.port("bottom", 0.5), story.port("bottom", 0.5), via=[(712, 305), (290, 305)], step=4,
       label="未完なら次の周", label_t=0.5, label_pos="below")
d.edge(tech.port("bottom", 0.5), deliver, via=[(712, 440)], step=5, label="全セクション完成",
       label_t=0.8, label_pos="below")
d.edge((800, 492), appi, style="dashed", color=TELEM, label="OTel トレース", label_t=0.5, label_dy=-12)

d.steps_panel(40, 630, 1460, [
    "CLI が GameSpec(15 項目)からタスク文を作る",
    "各ターンで gpt-5.4-mini を呼ぶ(計 8 回)",
    "1 周目は要約、2 周目は詳細を context に追記",
    "未完なら tech → story のループエッジで次の周へ",
    "4 セクションが揃ったら deliver が企画書にまとめる",
], columns=3)

d.notes(
    [
        ("運用", NOTE_SHARED_ONLY_JA),
        ("実測", "トレースで executor.process が役割ごとに 2 件+deliver 1 件 = ループエッジの発火がスパン数で見える"),
        ("注意", "HandoffBuilder 変種はリング順・フェーズ・終了がプロンプト頼み(呼び忘れは autonomous の nudge で復帰)"),
        ("認証", "モデル = API キー(ラボの .env)/ トレース = App Insights 接続文字列"),
        ("閉域", "ラボ構成: パブリックエンドポイント・VNet なし(閉域版は survey architecture 07)"),
    ],
    source="出典: labs/maf-ports/ports/game-design-team/README.md",
)

d.save(str(_here.parent / "architecture.png"))

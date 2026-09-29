"""governed-agent(Port 14)のアーキテクチャ図(v2 スタイル: 日本語+処理順バッジ)。

Regenerate(labs/maf-ports で):
    uv run --with diagrams,pillow python ports/governed-agent/docs/architecture.py
"""

import sys
from pathlib import Path

_here = Path(__file__).resolve()
_tools = next(p / "tools" for p in _here.parents if (p / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_tools))

from archdiagram import BLUE, MUTED, ORANGE, TELEM, Diagram, icon, std_azure

GATE_FILL = (255, 248, 230)
GATE_BORDER = (196, 140, 40)

d = Diagram(
    "governed-agent — MAF middleware によるガバナンス層(Port 14)",
    width=1560,
    height=1100,
    subtitle="経費精算の 3 段パイプライン(intake → inspector → approver)に、実行前のポリシー判定・"
    "信頼ゲート + HITL・SHA-256 ハッシュ連鎖の監査をアプリ層で重ねる",
)

# --- ローカル(uv + MAF) -----------------------------------------------------------
local = d.cluster(40, 100, 990, 650, "ローカル PC(uv + MAF)", kind="local")
cli = d.node(122, 195, icon("cli"), "CLI\ngoverned-agent-maf")
intake = d.box(290, 195, 140, 50, "intake\n(ExpenseClaim)")
gate1 = d.box(445, 195, 130, 50, "信頼ゲート ①\n閾値未満 → HITL", fill=GATE_FILL, border=GATE_BORDER)
inspector = d.box(610, 195, 150, 50, "inspector\n(InspectionReport)")
gate2 = d.box(775, 195, 130, 50, "信頼ゲート ②\n閾値未満 → HITL", fill=GATE_FILL, border=GATE_BORDER)

mw = d.cluster(430, 280, 850, 630, "approver + middleware(外 → 内)", kind="focus")
agent_audit = d.box(640, 345, 320, 40, "AgentAuditMiddleware(run 全体)")
tool_audit = d.box(640, 415, 320, 40, "ToolAuditMiddleware(遮断も記録)")
policy = d.box(640, 492, 320, 48, "PolicyEnforcementMiddleware\n(許可リスト・営業時間・金額)")
tools = d.box(640, 585, 280, 40, "経費ツール(submit / lookup / budget)")

audit = d.node(265, tool_audit.cy, icon("files"), "監査連鎖(SHA-256)", note="--audit-export → --verify")
d.text(265, 500, "入出力はハッシュのみ保持\n改ざん・削除・並べ替えを検知", fill=MUTED, anchor="ma")
hitl = d.node(920, 492, icon("user"), "HITL キュー", icon_size=52, note="チケット(スタブ)")

# --- Azure(共有基盤のみ) --------------------------------------------------------------
shared = std_azure(
    d, x0=1020, y0=100, x1=1520, y1=650, base="mafportsw3", rg="rg-maf-ports-w3", foundry_h=250,
    ja=True, model_note="3 エージェント共通",
)

# --- 辺 ----------------------------------------------------------------------------
d.edge(cli, intake, step=1)
d.edge(intake, gate1)
d.edge(gate1, inspector)
d.edge(inspector, gate2)
d.edge(gate2.port("bottom"), (gate2.cx, agent_audit.y0), label="通過", label_t=0.5, label_dx=24,
       label_dy=0)
d.edge(gate2.port("right"), hitl, via=[(hitl.cx, gate2.cy)], step=3, label="閾値未満", label_t=0.35,
       label_pos="above")
d.edge(agent_audit, tool_audit)
d.edge(tool_audit, policy, step=4, label="実行前に判定", label_t=0.5, label_pos="right")
d.edge(policy, tools, step=5, label="許可のみ実行", label_t=0.5, label_pos="right")
d.edge(policy.port("right"), hitl, label="AMT-002", label_color=ORANGE, label_t=0.5, label_dy=-12)
d.edge(tool_audit.port("left"), audit, step=6, label="全呼び出し", label_t=0.4, label_pos="above")
d.edge(agent_audit.port("left"), audit, label="run", label_t=0.4, label_dy=-10)
d.edge(local.port("right", (shared["model"].cy - 100) / 550), shared["model"], step=2,
       label="api-key", label_color=BLUE, label_t=0.55, label_pos="above")
d.edge(local.port("right", (shared["appi"].cy - 100) / 550), shared["appi"], style="dashed",
       color=TELEM, label="OTel トレース", label_t=0.5, label_dy=-12)

# --- 処理の流れ(下段) ----------------------------------------------------------------
d.steps_panel(40, 680, 1520, [
    "CLI の申請テキストを intake が構造化する",
    "3 エージェントがモデルを呼ぶ(api-key)",
    "各段の出力を決定論で採点、閾値未満は HITL へ",
    "approver のツール呼び出しを実行前に判定",
    "許可のみ実行。拒否・保留は理由を結果で返す",
    "全操作をハッシュ連鎖へ(--verify で検証)",
], columns=3)

d.notes(
    [
        ("制約", ("金額上限・営業時間・許可リストは Foundry ガードレール(Content Safety 系・"
                  "エージェント向けは Preview)では書けず、アプリ層に残る")),
        ("注意", ("遮断した呼び出しは実行されないため execute_tool スパンが出ない — "
                  "トレースでは「呼ばれなかった」と区別できず、監査連鎖が補う")),
        ("実測", ("2026-07-31 ライブ 2 本(20.1 秒): 正常承認が完走、上限超過は実行前に遮断され"
                  "モデルが拒否理由を説明して会話が続いた")),
        ("運用", ("インフラは共有基盤のみ(ポート固有リソースなし)。ポリシー・監査連鎖・HITL は"
                  "プロセス内、モデル呼び出しは api-key")),
        ("閉域", "ラボ構成: パブリックエンドポイント・VNet なし(閉域版は survey architecture 07)"),
    ],
    source="出典: labs/maf-ports/ports/governed-agent/README.md",
)

d.save(str(_here.parent / "architecture.png"))

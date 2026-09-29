"""travel-memory(Port 5)のアーキテクチャ図(v2 スタイル: 日本語+処理順バッジ)。

Regenerate(labs/maf-ports で):
    uv run --with diagrams,pillow python ports/travel-memory/docs/architecture.py
"""

import sys
from pathlib import Path

_here = Path(__file__).resolve()
for _p in _here.parents:
    if (_p / "tools" / "archdiagram.py").exists():
        sys.path.insert(0, str(_p / "tools"))
        break
from archdiagram import BLUE, EDGE, TELEM, Diagram, icon, std_azure

d = Diagram(
    "travel-memory — Foundry Memory で長期記憶付き旅行相談チャット(Port 5)",
    width=1500,
    height=900,
    subtitle="mem0 → Foundry Memory ストア。検索 → 注入 → 応答 → 追加を明示ループで回し、"
    "記憶は --user(= scope)ごとに分離",
)

# --- ローカル(左) ----------------------------------------------------------------
local = d.cluster(40, 100, 640, 700, "ローカル(uv + MAF)", kind="local")
d.cluster(185, 250, 620, 520, "1 ターン(chat.run_turn)", kind="focus")

cli = d.node(110, 389, icon("cli"), "CLI\ntravel-memory-maf")
d.node(
    110,
    195,
    icon("entra"),
    "az login",
    icon_size=48,
    note="Memory API 用(Entra ID)",
    note_color=BLUE,
)
d.node(110, 600, icon("keys"), ".env", icon_size=40, note="モデル用 api-key", note_color=BLUE)
turn = d.box(300, 389, 170, 58, "run_turn\n検索 → 注入 → 応答 → 追加")
agent = d.box(500, 318, 170, 50, "travel_agent\n(MAF Agent)")
store = d.box(500, 460, 170, 50, "FoundryMemoryStore\n(azure-ai-projects)")
d.edge(turn, agent)
d.edge(turn, store)

setup = d.box(410, 575, 330, 44, "scripts/setup_memory.py\nストア作成(初回のみ・Bicep 不可)")

# --- Azure(右): 共有基盤+埋め込み+Memory ストア -------------------------------------
shared = std_azure(d, x0=700, y0=100, x1=1460, y1=700, foundry_h=400, ja=True, model_note=None)
model, appi = shared["model"], shared["appi"]  # model (935, 318) / project (1225, 318)
embed = d.node(1080, 222, icon("model"), "埋め込み: text-embedding-3-small", icon_size=48)
memory = d.node(935, 460, icon("cache"), "Memory ストア\ntravel_memory", status="Preview")

# --- 処理の流れ ---------------------------------------------------------------------
d.edge(cli, turn, step=1, label_t=0.5)
d.edge(store, memory, both=True, step=2, label="検索", label_t=0.24, label_pos="above")
d.step(4, 818, 460)
d.text(818, 432, "追加(LRO)", anchor="ma", fill=EDGE)
d.text(750, 472, "Entra ID", fill=BLUE, anchor="ma")
d.edge(agent, model, step=3, label="api-key", label_color=BLUE, label_t=0.5, label_pos="above")
d.edge(memory, model, step=5, label="抽出・統合", label_t=0.5, label_pos="left")
d.edge(
    memory,
    embed,
    via=[(1080, 460)],
    label="プロジェクト MI",
    label_color=BLUE,
    label_t=0.9,
    label_dx=58,
    label_dy=0,
)

d.edge(
    setup,
    (903, 485),
    via=[(860, 575), (860, 485)],
    label="Entra ID",
    label_color=BLUE,
    label_t=0.3,
    label_dy=-12,
)
d.edge(
    (640, 620),
    (903, 620),
    style="dashed",
    color=TELEM,
    label="OTel トレース",
    label_t=0.5,
    label_dy=-12,
)

d.steps_panel(
    40,
    730,
    1460,
    [
        "--user(= scope)と質問を 1 ターン処理へ",
        "search_memories で関連記憶を検索",
        "記憶を注入したプロンプトで回答を生成",
        "user / assistant の発言を LRO で追加",
        "サービス側で記憶を抽出・統合(約 1 分)",
    ],
    columns=3,
)

d.notes(
    [
        (
            "制約",
            (
                "Memory はパブリックプレビュー(課金体系変更の可能性)。"
                "クォータ 100 scope/ストア・1 万件/scope・各 1,000 req/分"
            ),
        ),
        (
            "課金",
            "ストアのアイドル課金はなし。抽出・統合・検索のたびにストア構成の chat / 埋め込みモデルのトークンを消費",
        ),
        (
            "認証",
            "モデル = api-key / Memory Store API = Entra ID のみ(az login)/ ストア内のモデル呼び出し = プロジェクト MI",
        ),
        (
            "実測",
            "Bicep 作成のプロジェクト MI にモデル権限がなく search が 401 → roles.bicep で付与・伝播 5〜7 分(2026-07-31)",
        ),
        (
            "閉域",
            "ラボ構成: パブリックエンドポイント・VNet なし(閉域版は survey architecture 07)。Memory 自体も VNet 非対応",
        ),
    ],
    source="出典: labs/maf-ports/ports/travel-memory/README.md",
)

d.save(str(_here.parent / "architecture.png"))

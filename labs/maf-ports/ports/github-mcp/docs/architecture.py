"""github-mcp(Port 6)のアーキテクチャ図(v2 スタイル: 日本語+処理順バッジ)。

Regenerate(labs/maf-ports で):
    uv run --with diagrams,pillow python ports/github-mcp/docs/architecture.py
"""

import sys
from pathlib import Path

_here = Path(__file__).resolve()
for _p in _here.parents:
    if (_p / "tools" / "archdiagram.py").exists():
        sys.path.insert(0, str(_p / "tools"))
        break
from archdiagram import BLUE, EDGE, MUTED, TELEM, Diagram, icon, std_azure

d = Diagram(
    "github-mcp — MAF からリモート MCP を呼ぶ(Port 6)",
    width=1500,
    height=860,
    subtitle="stdio / Docker の MCP を GitHub 公式リモート MCP に置き換え。MCP 接続はクライアント側で完結し、"
    "ポート固有の Azure リソースはゼロ",
)

# --- ローカル(左上) --------------------------------------------------------------
local = d.cluster(40, 100, 660, 450, "ローカル(uv + MAF)", kind="local")
d.cluster(250, 200, 640, 420, "MCP クライアント(MAF)", kind="focus")

cli = d.node(120, 268, icon("cli"), "CLI\ngithub-mcp-maf")
agent = d.box(400, 268, 190, 52, "github_agent\n(MAF Agent)")
tool = d.box(400, 370, 280, 56, "MCPStreamableHTTPTool\nstatic_headers(同一オリジンのみ注入)")
d.edge(agent, tool, label="run 時に自動接続", label_t=0.5, label_dx=62, label_dy=0)

# --- GitHub(左下・Azure 外) -------------------------------------------------------
d.cluster(40, 490, 660, 660, "GitHub(Azure 外)", kind="external")
gh = d.node(400, 560, icon("github"), "GitHub 公式リモート MCP\napi.githubcopilot.com/mcp/")
d.text(
    60, 528, "元アプリは docker run で\nstdio サーバーを毎回起動\n→ リモート化で不要に", fill=MUTED
)
d.text(478, 522, "Authorization: Bearer <PAT>", fill=BLUE)
d.text(
    478,
    539,
    "X-MCP-Toolsets:\n  repos,issues,pull_requests\nX-MCP-Readonly: true(既定)",
    fill=MUTED,
)

# --- Azure(右) ------------------------------------------------------------------
shared = std_azure(
    d, x0=720, y0=100, x1=1460, y1=660, foundry_h=280, ja=True, model_note="GlobalStandard・容量 10"
)
model, appi = shared["model"], shared["appi"]  # model (945, 268)

# --- 処理の流れ ---------------------------------------------------------------------
d.edge(cli, agent, step=1, label_t=0.5)
d.edge(tool, gh, step=2, label="initialize / tools/list", label_t=0.3, label_pos="right")
d.step(4, 400, 507)
d.text(414, 500, "tools/call", fill=EDGE)
d.edge(
    agent,
    model,
    both=True,
    step=3,
    label="api-key",
    label_color=BLUE,
    label_t=0.45,
    label_pos="above",
)
d.step(5, 830, 268)
d.edge(
    local.port("right", 0.94),
    appi,
    style="dashed",
    color=TELEM,
    label="OTel トレース",
    label_t=0.5,
    label_dy=-12,
)

d.steps_panel(
    40,
    690,
    1460,
    [
        "質問に --repo を連結して Agent へ渡す",
        "initialize / tools/list で MCP に接続",
        "ツール一覧付きでモデルに問い合わせ",
        "モデルが選んだツールを tools/call",
        "ツール結果から Markdown で回答",
    ],
    columns=3,
)

d.notes(
    [
        (
            "認証",
            (
                "モデル = api-key / GitHub MCP = PAT を static_headers で送信"
                "(MAF 1.19+。MCP の URL と同一オリジンだけに注入)"
            ),
        ),
        (
            "注意",
            (
                "MAF 1.18 以前は static_headers を黙って無視し無認証で接続(401)。"
                "mcp 2.x も非互換のため mcp<2 に固定"
            ),
        ),
        (
            "推奨",
            "X-MCP-Readonly(既定 on)でサーバー側から書き込みツールを除去 — tools/list に現れない",
        ),
        (
            "課金",
            "Azure 側の追加リソース・課金なし(モデルのトークンのみ)。GitHub 側は PAT のレート制限のみ",
        ),
        (
            "閉域",
            (
                "ラボ構成: パブリックエンドポイント・VNet なし(閉域版は survey architecture 07)。"
                "MCP は端末から GitHub へ直接"
            ),
        ),
    ],
    source="出典: labs/maf-ports/ports/github-mcp/README.md",
)

d.save(str(_here.parent / "architecture.png"))

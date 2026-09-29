"""A1/A3/A4: Prompt agent + マネージドナレッジ 3 変種(04章)。同一骨格のため 1 枚に統合(v2 スタイル)。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/a1-prompt-rag-variants.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import (  # noqa: E402
    BLUE, EDGE, F_BOX, F_LABEL_B, INK, MUTED, ORANGE, TELEM, Diagram, az, icon, res,
)

d = Diagram(
    "A1 / A3 / A4: Prompt agent + マネージドナレッジ(骨格は同じ・ナレッジだけ 3 択)",
    width=1440,
    height=860,
    subtitle="最小のマネージド構成。ユーザー別の閲覧権限・メタデータ絞り込み・xlsx・閉域が要件に入ったら "
    "A2(自前索引)に上げる",
)

ROW = 280  # main request row

# --- 利用者(左) ------------------------------------------------------------------
d.cluster(40, 110, 205, 605, "利用者", kind="external")
user = d.node(122, ROW, res("onprem/client/user.png"), "社員", note="Entra ID サインイン")

# --- Azure --------------------------------------------------------------------
d.cluster(230, 100, 735, 615, "Azure サブスクリプション", kind="azure")
appsvc = d.node(335, ROW, az("appservices/app-services.png"), "App Service /\nWeb アプリ",
                note="マネージド ID")
appi = d.node(335, 480, icon("appinsights"), "App Insights", note="トレース")

fc = d.cluster(440, 145, 715, 600, "Foundry プロジェクト", kind="sub")
agent = d.node(578, ROW, icon("project"), "Prompt agent", status="GA")
model = d.node(578, 480, icon("model"), "モデルデプロイ", note="Global Standard")

# --- ナレッジ 3 択(右・この図の主題) ----------------------------------------------
kc = d.cluster(760, 110, 1400, 605, "ナレッジ ── A1 / A3 / A4 で差し替わるのはここだけ", kind="focus")
BUS_X = 792
ICON_X = 868
TEXT_X = 918
cards = [
    (200, icon("files"), "A1  File Search", "GA", [
        ("ファイルを上げるだけ。解析〜ハイブリッド検索・再ランクまで内蔵", INK),
        ("既定: チャンク 800 / 重複 400・3-large@256 次元(変更 API なし)", MUTED),
    ]),
    (360, icon("search"), "A3  AI Search ツール(既存インデックス)", "GA", [
        ("既存インデックス 1 本に直結(top_k 5・hybrid + semantic)", INK),
        ("同一テナント必須・認証はプロジェクト MI(閉域はキー不可)", BLUE),
    ]),
    (520, az("general/folder-website.png"), "A4  SharePoint ツール", "Preview", [
        ("実体は M365 Copilot Retrieval API。M365 の権限をそのまま透過", INK),
        ("OBO のみ(バッチ不可)・Copilot ライセンスか従量課金が要る", ORANGE),
    ]),
]
shapes = []
for cy, ic, title, status, lines in cards:
    s = d.node(ICON_X, cy, ic, "", icon_size=56)
    shapes.append((cy, s))
    ty = cy - 34
    d.text(TEXT_X, ty, title, font=F_LABEL_B, fill=INK)
    tw = d.d.textlength(title, font=F_LABEL_B)
    d.pill(TEXT_X + tw + 8, ty + 9, status)
    for i, (ln, col) in enumerate(lines):
        d.text(TEXT_X, ty + 26 + i * 20, ln, font=F_BOX, fill=col)

# --- 処理の流れ(下段) ------------------------------------------------------------
d.steps_panel(40, 632, 1400, [
    "社員が Entra ID でサインインして質問",
    "Web アプリがマネージド ID で agent を呼ぶ(Responses API)",
    "agent が A1 / A3 / A4 のどれかで検索",
    "モデルが検索結果から引用付きで回答",
], columns=2)

# --- edges --------------------------------------------------------------------
d.edge(user, appsvc, step=1, label_t=0.42)
d.edge(appsvc, agent, step=2, label_t=0.62)
d.edge(agent, (BUS_X, ROW), arrow=False, step=3, label_t=0.42)
d.d.line([(BUS_X, 200), (BUS_X, 520)], fill=EDGE, width=2)
for cy, s in shapes:
    d.edge((BUS_X, cy), (s.x0 - 2, cy))
d.edge(agent, model, step=4, label_t=0.5)
d.edge(fc.port("left", (480 - fc.y0) / (fc.y1 - fc.y0)), appi, style="dashed", color=TELEM)

d.notes(
    [
        ("制約", "A1 は文書単位 ACL・メタデータ絞り込み・xlsx / csv が不可 → どれかが要件に入った時点で A2 へ"),
        ("閉域", "閉域では A1 を提案しない(公式表は PE 経由で対応に変わったが、実測で vector store 作成が 500 で失敗)→ A2 / A3"),
        ("注意", "A3: AI Search ツールを含む会話では groundedness 等のエージェント評価器が使えない → CI 評価は A5 か自前ハーネス"),
        ("課金", "A1 = トークン + ベクトルストレージ(GB/日)/ A4 = M365 Copilot ライセンス(開発者・利用者とも)か Retrieval API 従量"),
        ("認証", "A4 は OBO のみ → バッチ・非対話型エージェントでは使えず、Teams に公開したエージェントでも動かない"),
    ],
    source="出典: docs/survey/architecture/04 A1・A3・A4",
)

d.save(
    str(_here.parent.parent / "images" / "a1-prompt-rag-variants.png"),
    slide=str(_here.parent.parent / "images" / "slide" / "a1-prompt-rag-variants.png"),
)

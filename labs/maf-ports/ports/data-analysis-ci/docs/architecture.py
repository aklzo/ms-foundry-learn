"""data-analysis-ci(Port 8)のアーキテクチャ図(v2 スタイル: 日本語+処理順バッジ)。

Regenerate(labs/maf-ports で):
    uv run --with diagrams,pillow python ports/data-analysis-ci/docs/architecture.py
"""

import sys
from pathlib import Path

_here = Path(__file__).resolve()
for _p in _here.parents:
    if (_p / "tools" / "archdiagram.py").exists():
        sys.path.insert(0, str(_p / "tools"))
        break
from archdiagram import BLUE, ORANGE, TELEM, Diagram, icon, std_azure

d = Diagram(
    "data-analysis-ci — Code Interpreter で CSV を自然言語分析(Port 8)",
    width=1500,
    height=900,
    subtitle="ローカルの DuckDB / pandas ツールをサーバー側 Code Interpreter に置き換え。"
    "CSV は Files API で渡り、Python は Azure のサンドボックスで動く",
)

# --- ローカル(左) ----------------------------------------------------------------
local = d.cluster(40, 100, 620, 720, "ローカル(uv + MAF)", kind="local")

data = d.node(
    120, 222, icon("files"), "data/sample_sales.csv", icon_size=48, note="同梱 30 行・正解は固定"
)
cli = d.node(120, 470, icon("cli"), "CLI\ndata-analysis-ci-maf")
d.node(
    400,
    610,
    icon("keys"),
    ".env",
    icon_size=40,
    note="api-key(Files / Responses 共通)",
    note_color=BLUE,
)
upload = d.box(400, 222, 230, 52, "validate + upload\n(クライアントに pandas なし)")
agent = d.box(400, 326, 230, 52, "data_analyst(MAF Agent)\n+ code_interpreter ツール dict")
extract = d.box(400, 470, 230, 52, "extract_analysis\n回答+実行コード+ログ")
d.edge(data, upload, label="data.csv", label_t=0.5, label_dy=-12)
d.edge(upload, agent, label="file-id", label_t=0.5, label_dx=34, label_dy=0)
d.edge(agent, extract, label="応答 Content", label_t=0.5, label_dx=52, label_dy=0)
d.edge(extract, cli, label="表示", label_t=0.5, label_dy=-12)

# --- Azure(右) ------------------------------------------------------------------
shared = std_azure(
    d, x0=680, y0=100, x1=1460, y1=720, base="mafportsw2", foundry_h=420, ja=True, model_note=None
)
model = shared["model"]  # (925, 326) / project (1215, 326)
files = d.node(1070, 222, icon("files"), "Files API(purpose=assistants)", icon_size=48)
ci = d.node(
    925,
    470,
    icon("container"),
    "Code Interpreter\nセッション(サンドボックス)",
    note="ネットワークなし・Hyper-V 分離",
    note_color=ORANGE,
    status="GA",
)

# --- 処理の流れ ---------------------------------------------------------------------
d.edge(upload, files, step=1, label="files.create", label_t=0.5, label_pos="above")
d.edge(
    agent,
    model,
    both=True,
    step=2,
    label="Responses API / api-key",
    label_color=BLUE,
    label_t=0.3,
    label_pos="above",
)
d.step(5, 790, 326)
d.edge(files, ci, via=[(1070, 470)], step=3, label="/mnt/data へ", label_t=0.75, label_pos="above")
d.edge(model, ci, step=4, label="pandas 実行", label_t=0.5, label_pos="left")
d.edge(
    local.port("right", 0.826),
    shared["appi"],
    style="dashed",
    color=TELEM,
    label="OTel トレース",
    label_t=0.5,
    label_dy=-12,
)

d.steps_panel(
    40,
    750,
    1460,
    [
        "CSV を検証し Files API にアップロード",
        "file_ids 付き code_interpreter で依頼",
        "ファイルがコンテナの /mnt/data に置かれる",
        "モデルが書いた pandas をサンドボックスで実行",
        "回答+実行コード・ログを受け取り抽出",
    ],
    columns=3,
)

d.notes(
    [
        (
            "課金",
            (
                "セッション課金(Responses 経路: 分単位・最低 5 分、20 分無操作で失効)。"
                "ARM リソースはないのに課金はある"
            ),
        ),
        (
            "注意",
            (
                "CSV は Files API で Azure 側へ渡る(データ持ち出し・DPA の検討対象)。"
                "アップロードは手で消すまで残る"
            ),
        ),
        (
            "制約",
            "サンドボックスはネットワークなし・Hyper-V 分離。ファイルは /mnt/data/{file-id}-{元の名前} に置かれる",
        ),
        (
            "認証",
            "Files / Responses API とも api-key(共有基盤の .env)/ トレースは App Insights 接続文字列",
        ),
        (
            "閉域",
            (
                "ラボ構成: パブリックエンドポイント・VNet なし(閉域版は survey architecture 07)。"
                "インフラは共有基盤のみ"
            ),
        ),
    ],
    source="出典: labs/maf-ports/ports/data-analysis-ci/README.md",
)

d.save(str(_here.parent / "architecture.png"))

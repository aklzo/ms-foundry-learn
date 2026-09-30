"""delegated-access-hosted(Port 15)のアーキテクチャ図(v2 スタイル: 日本語+処理順バッジ)。

Regenerate(labs/maf-ports で):
    uv run --with diagrams,pillow python ports/delegated-access-hosted/docs/architecture.py
"""

import sys
from pathlib import Path

_here = Path(__file__).resolve()
for _p in _here.parents:
    if (_p / "tools" / "archdiagram.py").exists():
        sys.path.insert(0, str(_p / "tools"))
        break
from archdiagram import BLUE, ORANGE, TELEM, Diagram, az, icon

d = Diagram(
    "delegated-access-hosted — hosted agent × 利用者の委任権限(OBO)(Port 15)",
    width=1660,
    height=900,
    subtitle="エージェントにできることを利用者ごとに変える: 中間層が OBO した委任トークンを x-client-* で転送し、"
    "最終判定は APIM(方式 A)か MCP サーバー自身(方式 B)が行う",
)

# --- 利用者側(ラボでは中間層も手元で起動)--------------------------------------------
d.cluster(30, 110, 330, 640, "利用者側", kind="local", sublabel="ラボでは中間層も手元")
cli = d.node(180, 205, icon("user"), "CLI(delegated-access)\n利用者ごとのトークンキャッシュ",
             icon_size=52)
backend = d.box(180, 450, 250, 62, "中間層バックエンド(FastAPI)\nトークン検証・OBO・ヘッダー 3 つ",
                status="自前")
d.text(180, 492, "追加認証が要るときは\n401+claims を CLI へ返す", anchor="ma")

# --- Entra ID(Azure サブスクリプションの外)---------------------------------------------
d.cluster(365, 110, 615, 300, "Microsoft Entra ID", kind="external")
entra = d.node(478, 205, icon("entra"), "アプリ登録 2 つ", note="dah-backend-api / dah-tools-api")

# --- Azure --------------------------------------------------------------------------
d.cluster(645, 100, 1630, 640, "Azure サブスクリプション — 共有基盤の RG(Japan East)", kind="azure")
d.cluster(665, 140, 985, 620, "Foundry プロジェクト: maf-ports", kind="sub")
model = d.node(830, 225, icon("model"), "モデルデプロイ", status="GA", note="agent identity で呼ぶ",
               note_color=BLUE)
d.cluster(683, 340, 967, 604, "hosted agent", kind="focus")
hosted = d.node(830, 450, icon("containerapp"), "Responses ハンドラー\nプロトコル 2.0.0", status="GA",
                note="方式 A / B で 1 つずつ")
tools_box = d.box(830, 568, 250, 42, "要求ごとに MAF Agent を組む\n見えた MCP ツールだけ持たせる")
d.edge(hosted, model)

apim = d.node(1100, 250, az("integration/api-management-services.png"), "API Management\nConsumption",
              note="validate-jwt: aud・scp・roles")
d.cluster(1200, 175, 1470, 560, "Container Apps(MCP ×3 を 1 アプリに)", kind="sub")
gw = d.box(1335, 250, 236, 52, "ca-dah-tools-gw\nENFORCEMENT_MODE=apim")
d.text(1335, 285, "署名・期限+共有シークレットだけ", anchor="ma")
srv = d.box(1335, 450, 236, 52, "ca-dah-tools-srv\nENFORCEMENT_MODE=server")
d.text(1335, 485, "JWT とロールを自分で判定", anchor="ma")
search = d.node(1552, 450, icon("search"), "AI Search Free", note="security filter")
d.edge(apim, gw)

# --- 処理の流れ(下段)-------------------------------------------------------------------
d.steps_panel(30, 670, 1630, [
    "CLI がデバイスコードで利用者トークン(aud = 中間層)を取得",
    "CLI → 中間層 POST /chat(Bearer 利用者トークン)",
    "中間層が OBO でツール API 宛ての委任トークンに交換",
    "Foundry へ Foundry 用トークン+x-client-tools-access-token+x-ms-user-identity",
    "方式 A: APIM が aud・scp・roles を判定して転送",
    "方式 B: MCP サーバー自身が JWT とロールを判定",
    "roles で文書を絞り込み、更新は oid で監査ログへ",
], columns=3, numbers=["1", "2", "3", "4", "A", "B", "5"])

# --- edges ------------------------------------------------------------------------------
d.edge(cli, entra, step=1, label="デバイスコード", label_color=BLUE, label_t=0.36,
       label_pos="above")
d.edge(cli, backend, step=2, label="利用者トークン", label_color=BLUE, label_t=0.45)
d.edge((305, 434.5), (512, 205), via=[(595, 434.5), (595, 205)], step=3,
       label="OBO", label_color=BLUE, label_t=0.3, label_pos="above")
d.edge((305, 465.5), (792, 465.5), step=4, label="ヘッダー 3 つ", label_color=BLUE,
       label_t=0.5, label_pos="below")
d.edge((868, 440), apim, via=[(1003, 440), (1003, 250)], step="A",
       label="委任トークン", label_color=BLUE, label_t=0.45, label_pos="right")
d.edge((868, 460), srv, via=[(1217, 460)], step="B",
       label="委任トークン", label_color=BLUE, label_t=0.62, label_pos="below")
d.edge(gw, search, via=[(1552, 250)], step=5, label="roles で絞る", label_t=0.72, label_pos="left")
d.edge(srv, search)

d.notes(
    [
        ("認証", (
            "Foundry は委任トークンを交換も更新もせず x-client-* を転送するだけ(Authorization は転送しない)。"
            "失効・追加認証は 401+claims を CLI まで返し、app-only へは切り替えない"
        )),
        ("制約", (
            "APIM Consumption: 1 要求 30 秒・SSE 非対応・MCP サーバー型なし → "
            "ステートレス Streamable HTTP(JSON 応答)を素の HTTP API として中継"
        )),
        ("注意", (
            "方式 A の裏のアプリも外部公開(Consumption は VNet 不可)。ロール判定は APIM だけなので、"
            "共有シークレットのないリクエストはサーバーが拒否する"
        )),
        ("運用", (
            "MAF の ResponsesHostServer はヘッダーをツールへ渡さない → Agent Server SDK のハンドラーで"
            "要求ごとに組む。resilient モードは client_headers(= トークン)を永続化するので使わない"
        )),
        ("課金", (
            "APIM Consumption・Container Apps(スケールゼロ)は従量、AI Search Free は無料(1 サブスク 1 つ)、"
            "hosted agent はセッション中の CPU/メモリ+トークン"
        )),
    ],
    source="出典: labs/maf-ports/ports/delegated-access-hosted/README.md",
)

d.save(str(_here.parent / "architecture.png"))

_ = (ORANGE, TELEM)  # 凡例の色(このポートではテレメトリ線を描かない)

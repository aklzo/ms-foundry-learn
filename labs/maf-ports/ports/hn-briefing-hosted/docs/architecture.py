"""hn-briefing-hosted(Port 11)のアーキテクチャ図(v2 スタイル: 日本語+処理順バッジ)。

Regenerate(labs/maf-ports で):
    uv run --with diagrams,pillow python ports/hn-briefing-hosted/docs/architecture.py
"""

import sys
from pathlib import Path

_here = Path(__file__).resolve()
for _p in _here.parents:
    if (_p / "tools" / "archdiagram.py").exists():
        sys.path.insert(0, str(_p / "tools"))
        break
from archdiagram import BLUE, ORANGE, TELEM, Diagram, icon, res

d = Diagram(
    "hn-briefing-hosted — hosted agent + Routines(Port 11)",
    width=1500,
    height=900,
    subtitle="唯一 Foundry 上で動くポート。エージェントはマネージドコンテナで実行し、常時稼働の運用グルー"
    "(スケジューラ・HTTP サーバー・認証)はプラットフォーム側へ移る",
)

# --- ローカル(Azure 外・左): デプロイと Routine 操作だけ ----------------------------
d.cluster(40, 110, 290, 580, "ローカル", kind="local", sublabel="デプロイ・操作のみ")
deploy = d.box(165, 250, 214, 50, "deploy_hosted_agent.py\nzip → REMOTE_BUILD")
op = d.node(165, 345, res("onprem/client/user.png"), "運用者(az login)", icon_size=48)
routset = d.box(165, 450, 214, 50, "setup_routine.py\nREST(api-version=v1)")
d.edge(op, deploy)
d.edge(op, routset)

# --- Azure ----------------------------------------------------------------------------
d.cluster(315, 100, 1255, 730, "Azure サブスクリプション — rg-maf-ports(Japan East)", kind="azure")
d.cluster(335, 145, 1235, 565, "Foundry プロジェクト: maf-ports", kind="sub",
          sublabel="aif-mafportsw2・共有基盤(AIServices S0)")
routine = d.node(470, 450, icon("scheduler"), "Routine\nhn-briefing-daily", status="GA",
                 note="平日 9:00 JST・検証後 disable", note_color=ORANGE)
ha = d.cluster(600, 195, 950, 525, "hosted agent: hn-briefing-agent", kind="focus")
hosted = d.node(790, 330, icon("containerapp"), "ResponsesHostServer\n:8088・responses 2.0.0",
                status="GA", note="0.5 vCPU / 1 GiB・python_3_13")
tool = d.box(790, 470, 260, 50, "関数ツール collect_ranked_stories\nコンテナ内 httpx(Toolbox 不要)")
d.edge(hosted, tool)
model = d.node(1110, 330, icon("model"), "モデルデプロイ\ngpt-5.4-mini", status="GA",
               note="GlobalStandard, capacity 10")

appi = d.node(790, 640, icon("appinsights"), "App Insights\nappi-mafportsw2")
logw = d.node(1060, 640, icon("loganalytics"), "Log Analytics\nlog-mafportsw2")
d.edge(appi, logw)

# --- 外部 Web(Azure 外・右) -------------------------------------------------------------
d.cluster(1280, 110, 1460, 580, "外部 Web", kind="external", sublabel="Azure 外")
hn = d.node(1370, 470, icon("browser"), "HN Algolia API\nfront_page JSON", note="キーレス HTTPS")

# --- 処理の流れ(下段) -------------------------------------------------------------------
d.steps_panel(40, 760, 1460, [
    "zip を REMOTE_BUILD でデプロイし 100% ルーティング",
    "Routine を PUT(api-version=v1・プレビューヘッダーなし)",
    "平日 9:00 JST に Responses API でエージェントを起動",
    "関数ツールが HN を取得し、元実装の式で決定論ランク",
    "digest からモデルがブリーフを生成(agent identity)",
], columns=3)

# --- edges ----------------------------------------------------------------------------
d.edge(deploy, hosted, via=[(790, 250)], step=1, label="Entra ID", label_color=BLUE,
       label_t=0.26, label_pos="above")
d.edge(routset, routine, step=2, label="Entra ID", label_color=BLUE, label_t=0.68,
       label_pos="above")
d.edge(routine, hosted, via=[(625, 450), (625, 330)], step=3, label="Responses", label_t=0.15,
       label_pos="below")
d.edge(tool, hn, step=4, label="HTTPS GET", label_t=0.5, label_pos="above")
d.edge(hosted, model, step=5, label="agent identity", label_color=BLUE, label_t=0.75,
       label_pos="above")
d.edge(ha.port("bottom", (790 - 600) / (950 - 600)), appi, style="dashed", color=TELEM,
       label="OTel(接続文字列は自動注入)", label_t=0.72, label_dx=112, label_dy=0)

d.notes(
    [
        ("課金", (
            "アクティブセッションの CPU + メモリ(0.5 vCPU / 1 GiB)+ トークン。アイドル既定 15 分"
            "(2〜60 分で設定可)でスケールゼロ、cron 発火ごとにコールドスタート"
        )),
        ("運用", (
            "hosted agent と Routine は ARM 型のないデータプレーン・オブジェクト → Bicep は既存参照のみ、"
            "デプロイはスクリプト(バージョンは不変・常に 1 バージョン 100%)"
        )),
        ("注意", (
            "Routine の下流呼び出しは 1 試行 30 秒・最大 3 試行。コールドスタート込みで超えると"
            "再試行で重複実行になりうる → run history の所要時間で確認"
        )),
        ("認証", (
            "モデル = agent identity(コンテナに秘密なし)/ デプロイ・Routine 操作 = Entra ID(az login)"
            "/ ロジック層 CLI(hn-briefing-maf)= api-key / HN = キーレス"
        )),
        ("閉域", (
            "ラボ構成: パブリックエンドポイント・VNet なし(閉域版は survey architecture 07)。"
            "egress controls(Preview)を使うなら許可先は hn.algolia.com のみ"
        )),
    ],
    source="出典: labs/maf-ports/ports/hn-briefing-hosted/README.md",
)

d.save(str(_here.parent / "architecture.png"))

"""公式-B: Baseline Microsoft Foundry Chat(01章)のアーキテクチャ図(v2 スタイル: 日本語+処理順バッジ)。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/baseline-chat.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import ORANGE, RED, TELEM, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "公式-B: Baseline Microsoft Foundry Chat(AAC リファレンスアーキテクチャ)",
    width=1560,
    height=860,
    subtitle="ネットワーク分離・単一リージョン・ゾーン冗長。WAF が「AI ワークロードの推奨アーキテクチャ」と名指しする"
    "本番の出発点",
)

# --- インターネット(入口・左) ------------------------------------------------------
d.cluster(40, 110, 215, 625, "インターネット(入口)", kind="external")
user = d.node(128, 240, res("onprem/client/user.png"), "利用者\n(ブラウザ)")
ops = d.node(128, 470, res("onprem/client/user.png"), "運用者")

# --- Azure --------------------------------------------------------------------
d.cluster(240, 100, 1330, 640, "Azure サブスクリプション(単一リージョン・ゾーン冗長)", kind="azure")
d.cluster(258, 140, 1312, 622, "VNet", kind="sub", sublabel="全サブネットを NSG で制御・UDR で Firewall へ")

appgw = d.node(345, 240, az("network/application-gateway.png"), "Application Gateway\n+ WAF",
               note="TLS 終端・WAF 要調整")
appsvc = d.node(510, 240, az("appservices/app-services.png"), "App Service\n(チャット UI)",
                note="3 ゾーン・マネージド ID")

fc = d.cluster(630, 160, 950, 330, "Foundry(standard setup)", kind="focus")
agentsvc = d.node(712, 240, icon("foundry"), "Agent Service", status="GA")
project = d.node(870, 240, icon("project"), "プロジェクト", note="prompt / hosted agent")

pe = d.cluster(440, 370, 895, 605, "snet-privateEndpoints", kind="sub")
cosmos = d.node(530, 460, az("databases/azure-cosmos-db.png"), "Cosmos DB\n(会話履歴)", note="PITR は直近 7 日")
storage = d.node(672, 460, az("storage/storage-accounts.png"), "Storage\n(アップロード)")
search = d.node(815, 460, icon("search"), "AI Search\n(File Search 索引)", note="復元不可 → 正本は別に",
                note_color=ORANGE)

egress = d.box(1085, 240, 150, 52, "snet-agentsEgress\n(/24・委任)")
mcp = d.box(1085, 400, 170, 52, "snet-mcpServers(/24)\nprivate MCP サーバー")
fw = d.node(1242, 240, az("network/firewall.png"), "Azure Firewall", note="TLS 検査は禁止", note_color=RED)

bastion = d.node(330, 470, az("networking/bastions.png"), "Bastion")
jump = d.box(330, 575, 130, 40, "jump box /\nbuild agent VM")

# --- インターネット(出口・右) ------------------------------------------------------
d.cluster(1350, 110, 1520, 625, "インターネット(出口)", kind="external")
ext = d.node(1437, 240, icon("browser"), "外部ツール\n(MCP / API)", note="許可 FQDN のみ")
bing = d.node(1437, 470, az("general/search.png"), "Bing\n(web search)", note="api.bing.microsoft.com")

# --- 処理の流れ(下段) ------------------------------------------------------------
d.steps_panel(40, 662, 1520, [
    "利用者は唯一の公開入口 App Gateway へ",
    "WAF を通過しチャット UI(App Service)へ",
    "Private Endpoint 経由でエージェントを呼ぶ",
    "会話・ファイル・索引は自サブスクの PE 先に保持",
    "外部ツール呼び出しは egress サブネットから",
    "Firewall が許可した FQDN だけ外へ出す",
], columns=3)

# --- edges --------------------------------------------------------------------
d.edge(user, appgw, step=1, label_t=0.44)
d.edge(appgw, appsvc, step=2, label_t=0.5)
d.edge(appsvc, (fc.x0, 240), step=3, label_t=0.5)
d.edge(fc.port("bottom", 0.28), (fc.x0 + (fc.x1 - fc.x0) * 0.28, pe.y0), step=4, label="PE",
       label_t=0.5, label_pos="right")
d.edge((fc.x1, 240), egress, step=5, label_t=0.45)
d.edge(egress, fw)
d.edge(egress, mcp, label="TCP 443 / 31443", label_t=0.5, label_dx=58, label_dy=0)
d.edge(fw, ext, step=6, label_t=0.76)
d.edge((925, 330), bing, via=[(925, 470)], color=RED, label="egress を迂回", label_color=RED,
       label_t=0.62, label_dy=-13)
d.edge(ops, bastion)
d.edge(bastion, jump)
d.edge(jump, (pe.x0, 575), style="dashed", color=TELEM)

d.notes(
    [
        ("注意", "web search ツールは api.bing.microsoft.com を内部で呼び egress サブネットを迂回する → 全ツールの egress 適合を実測する"),
        ("制約", "Agent Service に組込み DR なし(複製・バックアップ・PITR なし)→ 復旧は再構築。Cosmos PITR・agent as code・削除ロックで補う"),
        ("閉域", "Firewall で TLS インスペクション禁止(接続が壊れる)。private MCP は snet-mcpServers(2026-08 追加)で VNet 内に閉じる"),
        ("課金", "高コストは Cosmos DB / AI Search / DDoS Protection。エージェントの非決定的なツール呼び出しで外部 API 費が跳ねる"),
        ("認証", "prompt agent はプロジェクト MI を共有(アクセスパターン別にプロジェクトを分割)/ 会話の per-user 認可はアプリ責務(BOLA)"),
    ],
    source="出典: docs/survey/architecture/01 §1-B(AAC baseline-microsoft-foundry-chat)",
)

d.save(
    str(_here.parent.parent / "images" / "baseline-chat.png"),
    slide=str(_here.parent.parent / "images" / "slide" / "baseline-chat.png"),
)

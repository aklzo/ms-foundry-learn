"""D1: 規制業種・閉域 BYO VNet(07章)のアーキテクチャ図(v2 スタイル: 日本語+処理順バッジ)。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/d1-closed-network.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import ORANGE, RED, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "D1: 規制業種・閉域 — BYO VNet(standard agent setup)",
    width=1560,
    height=860,
    subtitle="ネットワーク構成とデータストア構成(capability host / 後継の capability settings とも)は作成時にしか"
    "決められない(変更 = 再作成)。設計は「閉域で使えない機能」の一覧から始める",
)

# --- 社内ネットワーク(Azure 外・左) ---------------------------------------------------
d.cluster(40, 110, 250, 710, "社内ネットワーク", kind="external")
d.box(145, 215, 184, 64, "オンプレ DNS\n→ 168.63.129.16 へ転送\n(Private DNS ゾーン × 6)")
user = d.node(145, 470, res("onprem/client/user.png"), "利用者", note="ExpressRoute / VPN")

# --- Azure ------------------------------------------------------------------------
d.cluster(280, 100, 1290, 730, "Azure サブスクリプション", kind="azure", sublabel="Foundry と VNet は同一リージョン")

d.cluster(300, 140, 830, 300, "Foundry(standard agent setup)", kind="sub")
acct = d.node(390, 205, icon("foundry"), "Foundry アカウント", note="公開アクセス無効")
proj = d.node(560, 205, icon("project"), "プロジェクト", note="データストア構成は変更不可", note_color=RED)
model = d.node(735, 205, icon("model"), "モデルデプロイ", note="Regional Standard")

d.cluster(860, 140, 1270, 300, "BYO データ", kind="sub", sublabel="すべて PE 経由")
cosmos = d.node(960, 205, az("databases/azure-cosmos-db.png"), "Cosmos DB", note="3,000 RU/s 以上")
storage = d.node(1085, 205, az("storage/storage-accounts.png"), "Storage")
search = d.node(1205, 205, icon("search"), "AI Search", note="閉域 RAG の本命")

d.cluster(300, 330, 1270, 710, "VNet", kind="sub")
d.text(318, 665, "RFC1918 のみ\n172.17.0.0/16 は不可")
pe_f = d.node(390, 470, az("network/private-endpoint.png"), "PE", note="Approved のみ", icon_size=52)

d.cluster(460, 380, 880, 690, "委任サブネット", kind="focus", sublabel="作成時のみ注入・/24・名前 ≤ 63 バイト")
vm = d.node(560, 470, icon("containerapp"), "hosted agent\n(Micro VM)", status="GA")
tools = d.box(760, 470, 150, 38, "Tools Service")
proxy = d.box(760, 555, 150, 44, "Data Proxy\n(single-tenant)")
egress = d.box(560, 640, 160, 36, "egress controls", status="Preview")

pe_d = d.node(960, 555, az("network/private-endpoint.png"), "PE × 3", note="自動作成されない",
              note_color=ORANGE, icon_size=48)
fw = d.node(1150, 640, az("network/firewall.png"), "Azure Firewall", note="TLS インスペクション禁止",
            note_color=RED, icon_size=56)

# --- Microsoft 管理の公開エンドポイント(Azure 外・右) -------------------------------------
d.cluster(1320, 110, 1520, 710, "公開エンドポイント", kind="external")
pub = d.box(1420, 205, 170, 52, "Bing / Web search\nSharePoint / Work IQ", border=(200, 120, 120))
d.text(1420, 238, "動くが公開経由", fill=RED, anchor="ma")
ms = d.node(1420, 640, icon("entra"), "Entra ID / Monitor", note="サービスタグで許可", icon_size=56)

# --- 処理の流れ(下段) ----------------------------------------------------------------
d.steps_panel(40, 760, 1520, [
    "社内から ER / VPN で PE へ(公開経路なし)",
    "委任サブネットに hosted agent セッションを起動",
    "ツール呼び出しは single-tenant の Data Proxy 経由",
    "PE 経由で BYO データへ(PE は個別に作成)",
    "送信は egress controls → Firewall で FQDN 許可",
], columns=3)

# --- edges ------------------------------------------------------------------------
d.edge(user, pe_f, both=True, step=1, label_t=0.5)
d.edge(pe_f, acct)
d.edge((560, 280), (560, 436), step=2, label_t=0.5)
d.edge(vm, tools)
d.edge(tools, proxy, step=3, label_t=0.5, label_pos="right")
d.edge(proxy, pe_d)
d.edge((960, 528), (960, 280), step=4, label_t=0.5)
d.edge((560, 547), egress)
d.edge(egress, fw, step=5, label_t=0.5)
d.edge(fw, ms)

d.notes(
    [
        ("制約", "閉域非対応: Memory・Logic Apps・Browser Automation・Computer Use・Image Generation・Fabric Data Agent。Tracing VNet はプレビュー"),
        ("注意", "Bing / Web search / SharePoint / Work IQ は動くが公開経由(web search は egress サブネットも迂回)→ 全閉域要件なら Policy で禁止"),
        ("実測", "hosted agent は公開アクセス無効だと VNet 注入(作成時のみ)が実質必須。注入なしはデプロイ成功・実行だけ失敗"),
        ("実測", "File Search は公式表記「PE 経由で対応」だが閉域アカウントで vector store 作成が 500 → AI Search ツールに寄せる"),
        ("閉域", "出口 Firewall の TLS インスペクション禁止(証明書が接続を壊す)→ 金融の SSL 可視化ポリシーと衝突。例外承認を初期に取る"),
    ],
    source="出典: docs/survey/architecture/07 §2〜3",
)

d.save(
    str(_here.parent.parent / "images" / "d1-closed-network.png"),
    slide=str(_here.parent.parent / "images" / "slide" / "d1-closed-network.png"),
)

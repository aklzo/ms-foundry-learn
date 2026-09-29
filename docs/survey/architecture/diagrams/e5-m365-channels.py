"""E5: M365 / Teams 連携(08章)のアーキテクチャ図(v2 スタイル: 日本語+処理順バッジ)。

Regenerate:  uv run --with diagrams,pillow python docs/survey/architecture/diagrams/e5-m365-channels.py
"""

from pathlib import Path
import sys

_here = Path(__file__).resolve()
_repo = next(p for p in _here.parents if (p / "labs" / "maf-ports" / "tools" / "archdiagram.py").exists())
sys.path.insert(0, str(_repo / "labs" / "maf-ports" / "tools"))
from archdiagram import BLUE, Diagram, az, icon, res  # noqa: E402

d = Diagram(
    "E5: Teams / M365 Copilot への公開と Copilot Studio 連携",
    width=1530,
    height=800,
    subtitle="Foundry → Teams / M365 Copilot の公開は GA(Responses から Activity プロトコルへ自動ブリッジ)。"
    "逆方向の Copilot Studio → Foundry 接続はプレビュー",
)

Y1, YM, Y2 = 250, 360, 470

# --- Microsoft 365(チャネル、Azure 外・左) --------------------------------------
d.cluster(40, 110, 420, 555, "Microsoft 365(チャネル)", kind="external")
users = d.node(115, YM, res("onprem/client/users.png"), "利用者")
teams = d.node(315, Y1, res("saas/chat/teams.png"), "Teams /\nM365 Copilot", note="エージェントストア", icon_size=80)
cs = d.node(315, Y2, az("integration/power-platform.png"), "Copilot Studio", note="業務部門のエージェント")

# --- Azure --------------------------------------------------------------------
d.cluster(450, 100, 1170, 585, "Azure サブスクリプション", kind="azure")
bot = d.node(565, Y1, az("aimachinelearning/bot-services.png"), "Bot Service", note="Microsoft.BotService")

d.cluster(670, 140, 1150, 555, "Foundry プロジェクト", kind="focus")
act = d.box(790, YM, 128, 48, "Activity\nエンドポイント")
agent = d.node(1030, YM, icon("foundry"), "Foundry エージェント\n(Prompt / Hosted)", note="安定エンドポイント")

# --- Work IQ(Azure 外・右) -------------------------------------------------------
d.cluster(1195, 110, 1490, 555, "Microsoft 365(業務文脈)", kind="external")
wiq = d.node(1342, YM, az("integration/software-as-a-service.png"), "Work IQ", status="Preview",
             note="メール・会議・ファイル・チャット")

# --- edges --------------------------------------------------------------------
# 1: 公開(Teams アプリ マニフェスト化 → エージェントストア)
d.edge(agent.port("top"), teams.port("top"), via=[(1030, 180), (315, 180)], step=1, label="公開",
       label_t=0.686, label_pos="above")
d.pill(582, 159, "GA")  # 公開フロー = GA
# 2: 利用者 → Teams / Copilot Studio
d.edge(users, teams, via=[(205, YM), (205, Y1)], step=2, label_t=0.78)
d.edge(users, cs, via=[(205, YM), (205, Y2)])
# 3: Bot Service が Activity で中継
d.edge(teams, bot, step=3, label_t=0.5)
d.edge(bot, act, via=[(790, Y1)])
d.edge(act, agent, label="Responses へ\n自動ブリッジ", label_t=0.5, label_dy=-22)
# 4: Work IQ(OBO)
d.edge(agent, wiq, step=4, label="OBO", label_color=BLUE, label_t=0.2, label_pos="above")
# 5: Copilot Studio → 接続エージェント(プレビュー)
d.edge(cs, act, via=[(790, Y2)], step=5, label="接続エージェント", label_t=0.35, label_pos="below")
d.pill(582, Y2 + 23, "Preview", anchor="lm")  # Copilot Studio → Foundry 接続 = プレビュー

d.steps_panel(40, 610, 1490, [
    "Teams アプリとして公開(組織公開は管理者承認)",
    "利用者が Teams / M365 Copilot から呼ぶ",
    "Bot Service が Activity プロトコルで中継",
    "Work IQ で M365 の業務文脈を参照(OBO)",
    "Copilot Studio から接続エージェントとして呼ぶ",
], columns=3)

d.notes(
    [
        ("課金", "publisher-pays: 発行者がインフラ費用を負担し、エンドユーザーは既定で課金されない → 社内展開の費用設計に入れる"),
        ("閉域", "PNA 無効ならポータル公開不可・REST のみ(enable_m365_public_endpoint で Activity ルートだけ公開)。Azure Government は非対応"),
        ("認証", "OAuth OBO(ユーザートークン)か、エージェント自身の ID(自律・バックグラウンド)の 2 モード"),
        ("制約", "Copilot Studio 接続は新ポータル作成のエージェントのみ(Activity 有効化は REST / SDK)。旧 Agent Applications 形式は新規公開不可"),
        ("注意", "Work IQ は Global Admin のテナント同意と BYO Entra アプリ(OBO)が前提。宛先は公開 HTTPS で閉域要件は満たさない"),
    ],
    source="出典: docs/survey/architecture/08 E5",
)

d.save(
    str(_here.parent.parent / "images" / "e5-m365-channels.png"),
    slide=str(_here.parent.parent / "images" / "slide" / "e5-m365-channels.png"),
)

"""通信グラフ(Agency Swarm の communication_flows)を**データ**として定義する。

元アプリの Agency(...) 呼び出し:

    communication_flows=[
        (ceo, cto), (ceo, product_manager), (ceo, developer), (ceo, client_manager),
        (cto, developer), (product_manager, developer), (product_manager, client_manager),
    ]

Agency Swarm では (sender, recipient) の**有向**ペアが「sender が recipient への
send_message ツールを持つ」ことを意味する(元 README の「CEO ↔ All Agents」の
双方向矢印はコード上は一方向)。移植でもこの向きをそのまま保存し、このタプル列
から talk_to_<recipient> ツールを生成する(agency.py の :func:`make_talk_tool`)。

グラフの性質(テストで固定): 本グラフは DAG で最長パスは 2 ホップ
(ceo→cto→developer / ceo→product_manager→{developer,client_manager})。
つまり実グラフでは再帰深度 3 の打ち切りに到達しない — 深度制御は「グラフを
書き換えて循環を入れたとき」の安全弁として機能する(comms.py)。
"""

from __future__ import annotations

from collections.abc import Sequence

#: エージェントのキー(元アプリの変数名を踏襲)。トップレベル実行の順でもある。
AGENT_KEYS: tuple[str, ...] = ("ceo", "cto", "product_manager", "developer", "client_manager")

#: 元アプリの Agent(name=...) — 表示・ログ・ツール docstring に使う
DISPLAY_NAMES: dict[str, str] = {
    "ceo": "Project Director",
    "cto": "Technical Architect",
    "product_manager": "Product Manager",
    "developer": "Lead Developer",
    "client_manager": "Client Success Manager",
}

#: 元アプリの Agent(description=...) 原文 — talk_to_* ツールの docstring に使う
DESCRIPTIONS: dict[str, str] = {
    "ceo": (
        "You are a CEO of multiple companies in the past and have a lot of experience "
        "in evaluating projects and making strategic decisions."
    ),
    "cto": "Senior technical architect with deep expertise in system design.",
    "product_manager": "Experienced product manager focused on delivery excellence.",
    "developer": "Senior developer with full-stack expertise.",
    "client_manager": "Experienced client manager focused on project delivery.",
}

#: 元アプリの communication_flows 原文(有向。sender → recipient)
COMMUNICATION_FLOWS: tuple[tuple[str, str], ...] = (
    ("ceo", "cto"),
    ("ceo", "product_manager"),
    ("ceo", "developer"),
    ("ceo", "client_manager"),
    ("cto", "developer"),
    ("product_manager", "developer"),
    ("product_manager", "client_manager"),
)

Flows = Sequence[tuple[str, str]]


def validate_flows(flows: Flows, agent_keys: Sequence[str] = AGENT_KEYS) -> None:
    """通信グラフの整合性検査(未知キー・自己ループ・重複を拒否)。"""
    known = set(agent_keys)
    seen: set[tuple[str, str]] = set()
    for pair in flows:
        sender, recipient = pair
        if sender not in known:
            raise ValueError(f"communication_flows: 未知の sender '{sender}'")
        if recipient not in known:
            raise ValueError(f"communication_flows: 未知の recipient '{recipient}'")
        if sender == recipient:
            raise ValueError(f"communication_flows: 自己ループ '{sender}' は許可しない")
        if (sender, recipient) in seen:
            raise ValueError(f"communication_flows: 重複ペア {pair}")
        seen.add((sender, recipient))


def allowed_recipients(sender: str, flows: Flows = COMMUNICATION_FLOWS) -> tuple[str, ...]:
    """sender が会話を開始できる相手(flows の記載順を保存)。"""
    return tuple(recipient for s, recipient in flows if s == sender)


def is_allowed(sender: str, recipient: str, flows: Flows = COMMUNICATION_FLOWS) -> bool:
    """有向ペア (sender, recipient) が許可されているか。向きが逆なら False。"""
    return (sender, recipient) in set(map(tuple, flows))


def talk_tool_name(recipient: str) -> str:
    """recipient への通信ツール名(例: talk_to_cto)。"""
    return f"talk_to_{recipient}"

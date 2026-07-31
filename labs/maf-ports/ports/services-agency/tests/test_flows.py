"""通信グラフ(flows.py)とツール生成(Agency.talk_tools)のオフラインテスト。

Port 13 の要点 (b): 選択肢は有向グラフで制約される — 許可ペアのみツールが
生成され、非許可ペアには**ツールが存在しない**ことを固定する。
"""

from itertools import product

import pytest

from services_agency_maf.agency import Agency
from services_agency_maf.flows import (
    AGENT_KEYS,
    COMMUNICATION_FLOWS,
    DISPLAY_NAMES,
    allowed_recipients,
    is_allowed,
    talk_tool_name,
    validate_flows,
)

# --- グラフ定義そのもの -----------------------------------------------------


def test_flows_match_original_agency_definition() -> None:
    """元アプリの communication_flows 7 ペア(向き込み)を保存する。"""
    assert COMMUNICATION_FLOWS == (
        ("ceo", "cto"),
        ("ceo", "product_manager"),
        ("ceo", "developer"),
        ("ceo", "client_manager"),
        ("cto", "developer"),
        ("product_manager", "developer"),
        ("product_manager", "client_manager"),
    )


def test_allowed_recipients_per_sender() -> None:
    assert allowed_recipients("ceo") == ("cto", "product_manager", "developer", "client_manager")
    assert allowed_recipients("cto") == ("developer",)
    assert allowed_recipients("product_manager") == ("developer", "client_manager")
    assert allowed_recipients("developer") == ()
    assert allowed_recipients("client_manager") == ()


def test_direction_matters() -> None:
    """有向グラフ: 逆向きは許可されない(元 README の ↔ 表記はコード上一方向)。"""
    assert is_allowed("ceo", "cto")
    assert not is_allowed("cto", "ceo")
    assert is_allowed("cto", "developer")
    assert not is_allowed("developer", "cto")
    assert not is_allowed("client_manager", "product_manager")


def test_graph_is_dag_with_max_two_hops() -> None:
    """実グラフは循環なし・最長 2 ホップ(深度打ち切りは安全弁であることの根拠)。"""
    # 出次数 0 の役割からは何も始まらない
    assert allowed_recipients("developer") == ()
    assert allowed_recipients("client_manager") == ()
    # 2 ホップ目の到達先(cto/product_manager の先)はすべて出次数 0
    for mid in ("cto", "product_manager"):
        for end in allowed_recipients(mid):
            assert allowed_recipients(end) == ()


def test_validate_flows_rejects_unknown_agent() -> None:
    with pytest.raises(ValueError, match="未知の sender"):
        validate_flows((("ghost", "ceo"),))
    with pytest.raises(ValueError, match="未知の recipient"):
        validate_flows((("ceo", "ghost"),))


def test_validate_flows_rejects_self_loop_and_duplicates() -> None:
    with pytest.raises(ValueError, match="自己ループ"):
        validate_flows((("ceo", "ceo"),))
    with pytest.raises(ValueError, match="重複ペア"):
        validate_flows((("ceo", "cto"), ("ceo", "cto")))


# --- ツール生成(グラフ → talk_to_*) --------------------------------------


def test_talk_tools_generated_only_for_allowed_pairs() -> None:
    agency = Agency()
    for sender in AGENT_KEYS:
        names = [tool.__name__ for tool in agency.talk_tools(sender)]
        assert names == [talk_tool_name(r) for r in allowed_recipients(sender)]


def test_no_tool_exists_for_disallowed_pairs() -> None:
    """非許可ペアにはツールが無い(プロンプト制約でなく構造制約)。"""
    agency = Agency()
    allowed = set(COMMUNICATION_FLOWS)
    for sender, recipient in product(AGENT_KEYS, AGENT_KEYS):
        if sender == recipient or (sender, recipient) in allowed:
            continue
        names = {tool.__name__ for tool in agency.talk_tools(sender)}
        assert talk_tool_name(recipient) not in names, f"{sender} -> {recipient}"


def test_sink_roles_have_no_talk_tools() -> None:
    agency = Agency()
    assert agency.talk_tools("developer") == []
    assert agency.talk_tools("client_manager") == []


def test_talk_tool_docstring_describes_recipient() -> None:
    """docstring(= モデルに見えるツール説明)に相手の表示名と description が載る。"""
    agency = Agency()
    (tool,) = agency.talk_tools("cto")
    assert tool.__name__ == "talk_to_developer"
    assert DISPLAY_NAMES["developer"] in tool.__doc__
    assert "full-stack expertise" in tool.__doc__
    assert "message:" in tool.__doc__


async def test_direct_call_of_disallowed_pair_raises() -> None:
    """防御的検査: ツールを迂回して call しても非許可ペアは通らない。"""
    agency = Agency()
    with pytest.raises(PermissionError, match="cto -> ceo"):
        await agency.call("cto", "ceo", "hello")


def test_custom_flows_change_generated_tools() -> None:
    """グラフはデータ — 差し替えればツールも変わる(生成であることの証明)。"""
    agency = Agency(flows=(("developer", "cto"),))
    names = [tool.__name__ for tool in agency.talk_tools("developer")]
    assert names == ["talk_to_cto"]
    assert agency.talk_tools("ceo") == []

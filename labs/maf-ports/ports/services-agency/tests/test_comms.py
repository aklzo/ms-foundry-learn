"""通信ログ(CommLog)と再帰深度制御のオフラインテスト。

深度打ち切りの検証には実グラフでは到達できない(DAG 最長 2 ホップ)ため、
循環グラフ ceo ⇄ cto を注入して安全弁の発火を確認する。
"""

import pytest
from conftest import ConsultingAgent, ScriptedAgent

from services_agency_maf.agency import Agency
from services_agency_maf.comms import (
    DEFAULT_MAX_DEPTH,
    CommLog,
    at_depth,
    current_depth,
)

# --- CommLog 単体 -----------------------------------------------------------


def test_events_get_sequential_seq_and_fields() -> None:
    log = CommLog()
    first = log.open("user", "ceo", 0, "start")
    second = log.open("ceo", "cto", 1, "help")
    log.complete(second, "sure")
    log.complete(first, "done")

    assert [event.seq for event in log.events] == [1, 2]
    assert first.to_dict() == {
        "seq": 1,
        "sender": "user",
        "recipient": "ceo",
        "depth": 0,
        "message": "start",
        "reply": "done",
        "blocked": False,
    }


def test_blocked_event_recorded_without_reply() -> None:
    log = CommLog()
    event = log.block("cto", "ceo", 4, "too deep")
    assert event.blocked is True
    assert event.reply is None
    assert "BLOCKED" in event.render()


def test_agent_pairs_excludes_user_and_blocked() -> None:
    log = CommLog()
    log.open("user", "ceo", 0, "start")
    log.open("ceo", "cto", 1, "help")
    log.block("cto", "ceo", 4, "too deep")

    assert log.agent_pairs() == [("ceo", "cto")]
    assert log.agent_pairs(include_blocked=True) == [("ceo", "cto"), ("cto", "ceo")]


def test_render_indents_by_depth_and_truncates() -> None:
    log = CommLog()
    log.open("user", "ceo", 0, "start")
    log.open("ceo", "cto", 1, "x" * 200)
    text = log.render()
    lines = text.splitlines()
    assert lines[0].startswith("#1 user -> ceo")
    assert lines[1].startswith("  #2 ceo -> cto")
    assert "..." in lines[1]
    assert len(lines[1]) < 200


def test_empty_log_renders_placeholder() -> None:
    assert CommLog().render() == "(no communications)"


def test_listener_receives_phases() -> None:
    seen: list[tuple[int, str]] = []
    log = CommLog(listener=lambda event, phase: seen.append((event.seq, phase)))
    event = log.open("user", "ceo", 0, "start")
    log.complete(event, "done")
    log.block("ceo", "cto", 4, "deep")

    assert seen == [(1, "ask"), (1, "reply"), (2, "blocked")]


# --- 深度の ContextVar ------------------------------------------------------


def test_depth_defaults_to_zero_and_restores() -> None:
    assert current_depth() == 0
    with at_depth(2):
        assert current_depth() == 2
        with at_depth(3):
            assert current_depth() == 3
        assert current_depth() == 2
    assert current_depth() == 0


# --- 深度打ち切り(循環グラフでの安全弁) -----------------------------------

#: 実グラフに無い循環を意図的に注入する(キーは実在の 2 役を流用)
CYCLE_FLOWS = (("ceo", "cto"), ("cto", "ceo"))


def make_cycle_agency(max_depth: int = DEFAULT_MAX_DEPTH) -> tuple[Agency, ConsultingAgent]:
    agency = Agency(flows=CYCLE_FLOWS, max_depth=max_depth)
    ceo = ConsultingAgent("ceo", [("cto", "ping")])
    cto = ConsultingAgent("cto", [("ceo", "pong")])
    agency.register("ceo", ceo)
    agency.register("cto", cto)
    ceo.bind(agency.talk_tools("ceo"))
    cto.bind(agency.talk_tools("cto"))
    return agency, ceo


async def test_infinite_ping_pong_is_cut_at_max_depth() -> None:
    """ceo ⇄ cto が互いを呼び続けても深度 3 で打ち切られ、実行が停止する。"""
    agency, _ = make_cycle_agency()
    text = await agency.get_response("ceo", "start")

    events = agency.log.events
    # user→ceo(0), ceo→cto(1), cto→ceo(2), ceo→cto(3), cto→ceo(4=blocked)
    assert [(e.sender, e.recipient, e.depth, e.blocked) for e in events] == [
        ("user", "ceo", 0, False),
        ("ceo", "cto", 1, False),
        ("cto", "ceo", 2, False),
        ("ceo", "cto", 3, False),
        ("cto", "ceo", 4, True),
    ]
    # ブロック通知はツール結果として送信側の応答に統合される
    assert "[communication blocked]" in text
    assert f"depth limit ({DEFAULT_MAX_DEPTH})" in text.lower()


async def test_blocked_call_returns_notice_not_exception() -> None:
    agency, _ = make_cycle_agency(max_depth=1)
    text = await agency.get_response("ceo", "start")

    # ceo→cto(1) は通り、cto→ceo(2) がブロック
    blocked = [event for event in agency.log.events if event.blocked]
    assert [(e.sender, e.recipient, e.depth) for e in blocked] == [("cto", "ceo", 2)]
    assert "[communication blocked]" in text


async def test_non_blocked_events_all_have_replies() -> None:
    agency, _ = make_cycle_agency()
    await agency.get_response("ceo", "start")
    for event in agency.log.events:
        if event.blocked:
            assert event.reply is None
        else:
            assert isinstance(event.reply, str) and event.reply


async def test_depth_resets_between_top_level_turns() -> None:
    """トップレベルターンをまたいで深度が持ち越されない。"""
    agency, _ = make_cycle_agency()
    await agency.get_response("ceo", "first")
    first_blocked = sum(1 for e in agency.log.events if e.blocked)
    await agency.get_response("ceo", "second")
    second_blocked = sum(1 for e in agency.log.events if e.blocked)

    # 2 回目のターンも同じ形(1 ブロックずつ増える)= 深度が 0 から数え直されている
    assert second_blocked == first_blocked + 1
    assert current_depth() == 0


async def test_max_depth_must_be_positive() -> None:
    with pytest.raises(ValueError, match="max_depth"):
        Agency(max_depth=0)


async def test_unregistered_agent_raises_clean_error() -> None:
    agency = Agency()
    with pytest.raises(KeyError, match="未登録"):
        await agency.get_response("ceo", "start")


async def test_register_unknown_key_rejected() -> None:
    agency = Agency()
    with pytest.raises(KeyError, match="未知"):
        agency.register("intern", ScriptedAgent("hi"))

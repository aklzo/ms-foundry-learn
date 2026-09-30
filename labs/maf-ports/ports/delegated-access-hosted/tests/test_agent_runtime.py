"""hosted agent の中身(DelegatedAccessRuntime)— 利用者ごとのツールの見え方と、失敗の扱い。

相手役は本物の MCP プロトコルで話す ``FakeToolsServer``(FakeEntra の JWT を検証し、契約の
ロールで 401 / 403 を返す)。モデルは ``ScriptedChatClient`` で、実 MAF Agent の
function-calling ループとミドルウェアは本物のまま回る。
"""

from __future__ import annotations

import logging

import pytest
from agent_framework import Message

from delegated_access_maf.agent import signals
from delegated_access_maf.agent.middleware import InMemoryAuditSink, RequestScope
from delegated_access_maf.agent.runtime import DelegatedAccessRuntime
from delegated_access_maf.agent.settings import AgentSettings
from delegated_access_maf.contracts import MSG_FORBIDDEN, MSG_REAUTH
from delegated_access_maf.devtools.fake_entra import USERS, FakeEntra
from delegated_access_maf.redaction import REDACTED, RedactingLogFilter
from tests.caller_fakes import (
    TOOLS_BASE_URL,
    FakeToolsServer,
    ScriptedChatClient,
    call_then_answer,
    last_tool_result,
    text_reply,
    tool_call_reply,
)

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.fixture
def entra() -> FakeEntra:
    return FakeEntra()


def tools_token(entra: FakeEntra, alias: str) -> str:
    return entra.obo_exchange(entra.issue_user_token(alias), entra.tools_scope)["access_token"]


def make_runtime(
    tools: FakeToolsServer, chat: ScriptedChatClient, audit: InMemoryAuditSink | None = None
):
    return DelegatedAccessRuntime(
        chat_client=chat,
        settings=AgentSettings(tools_base_url=TOOLS_BASE_URL),
        transport_factory=tools.transport,
        audit=audit or InMemoryAuditSink(),
    )


async def run(
    runtime: DelegatedAccessRuntime, token: str, question: str, user_id: str = "platform-user"
):
    return await runtime.run(
        token=token,
        messages=[Message("user", [question])],
        scope=RequestScope("caresp_test", user_id),
    )


# --- 利用者ごとのツールの見え方 ---------------------------------------------------------


@pytest.mark.parametrize(
    ("alias", "expected_tools", "hidden"),
    [
        ("employee", ["search_documents", "list_suppliers", "get_supplier"], ("supplier-admin",)),
        (
            "finance",
            ["search_documents", "list_suppliers", "get_supplier", "update_payment_terms"],
            (),
        ),
    ],
)
async def test_model_sees_only_the_tools_the_user_may_use(
    entra, alias, expected_tools, hidden
) -> None:
    chat = ScriptedChatClient([text_reply("ok")])
    async with FakeToolsServer(entra) as tools:
        outcome = await run(make_runtime(tools, chat), tools_token(entra, alias), "何ができますか")

    assert chat.calls[0].tool_names == expected_tools
    assert outcome.hidden_servers == hidden
    assert outcome.status == signals.STATUS_OK
    # 見えない MCP サーバーには initialize の 1 回だけ(403)で、ツール一覧も取りに行かない
    if hidden:
        admin = [r for r in tools.requests if r.server == "supplier-admin"]
        assert [(r.method, r.status) for r in admin] == [("initialize", 403)]


async def test_document_trimming_reaches_the_model_per_user(entra) -> None:
    """同じ質問でも、経理担当にだけ経理向け文書(与信限度額)がモデル入力に届く。"""
    seen: dict[str, str] = {}
    async with FakeToolsServer(entra) as tools:
        for alias in ("employee", "finance"):
            chat = ScriptedChatClient(
                call_then_answer(
                    "search_documents", {"query": "与信限度額"}, lambda c: last_tool_result(c)
                )
            )
            await run(
                make_runtime(tools, chat), tools_token(entra, alias), "与信限度額の見直し頻度は?"
            )
            seen[alias] = chat.calls[1].all_text()

    assert "与信限度額の運用" in seen["finance"]
    assert "与信限度額の運用" not in seen["employee"]
    assert "経費精算ガイド" in seen["employee"]


async def test_update_by_finance_executes_with_the_users_identity(entra) -> None:
    chat = ScriptedChatClient(
        call_then_answer(
            "update_payment_terms", {"supplier_id": "S-001", "days": 60}, "更新しました"
        )
    )
    audit = InMemoryAuditSink()
    async with FakeToolsServer(entra) as tools:
        outcome = await run(
            make_runtime(tools, chat, audit), tools_token(entra, "finance"), "S-001 を 60 日に"
        )

    assert outcome.text == "更新しました"
    assert tools.executed == [
        ("update_payment_terms", USERS["finance"].oid, {"supplier_id": "S-001", "days": 60})
    ]
    call = [e for e in audit.events if e.tool == "update_payment_terms"]
    assert [(e.decision, e.server, e.user_id) for e in call] == [
        ("allowed", "supplier-admin", "platform-user")
    ]


async def test_employee_update_request_never_reaches_the_update_tool(entra) -> None:
    """一般社員には更新ツールが無い — モデルが名前を知っていても実行経路が無い。"""
    chat = ScriptedChatClient(
        [
            tool_call_reply(("update_payment_terms", {"supplier_id": "S-001", "days": 60})),
            text_reply(MSG_FORBIDDEN),
        ]
    )
    async with FakeToolsServer(entra) as tools:
        outcome = await run(
            make_runtime(tools, chat), tools_token(entra, "employee"), "S-001 を 60 日に"
        )

    assert tools.executed == []
    assert not any(
        r.server == "supplier-admin" and r.method == "tools/call" for r in tools.requests
    )
    assert outcome.text == MSG_FORBIDDEN


# --- 呼び出し時点の拒否 -----------------------------------------------------------------


async def test_call_time_403_becomes_msg_forbidden_without_retry(entra) -> None:
    chat = ScriptedChatClient(
        call_then_answer("get_supplier", {"supplier_id": "S-001"}, lambda c: last_tool_result(c))
    )
    audit = InMemoryAuditSink()
    async with FakeToolsServer(entra, forbid_calls={"get_supplier"}) as tools:
        outcome = await run(
            make_runtime(tools, chat, audit), tools_token(entra, "employee"), "S-001 の支払条件"
        )

    # モデルには定型文だけが届き、利用者への回答もそれになる
    assert last_tool_result(chat.calls[1]) == MSG_FORBIDDEN
    assert outcome.text == MSG_FORBIDDEN
    assert outcome.forbidden_tools == ("get_supplier",)
    # 再接続・再送なし: tools/call はちょうど 1 回、送ったのは利用者のトークンだけ
    calls = tools.calls()
    assert [(c.tool, c.status) for c in calls] == [("get_supplier", 403)]
    assert {c.oid for c in tools.requests if c.oid} == {USERS["employee"].oid}
    assert [e.decision for e in audit.events if e.tool == "get_supplier"] == ["forbidden"]


async def test_call_time_401_stops_and_asks_for_reauthentication(entra) -> None:
    chat = ScriptedChatClient(call_then_answer("list_suppliers", {}, "この回答は使われない"))
    async with FakeToolsServer(entra, expire_calls={"list_suppliers"}) as tools:
        outcome = await run(make_runtime(tools, chat), tools_token(entra, "employee"), "取引先一覧")

    assert outcome.status == signals.STATUS_REAUTH
    assert outcome.reason == signals.REASON_TOOL_UNAUTHORIZED
    assert outcome.text == MSG_REAUTH
    assert 'error="invalid_token"' in outcome.www_authenticate
    assert len(chat.calls) == 1  # ツール結果を受けて再びモデルを呼ぶことはない
    assert [(c.tool, c.status) for c in tools.calls()] == [("list_suppliers", 401)]


async def test_invalid_token_at_discovery_skips_the_model(entra) -> None:
    other_tenant = FakeEntra(tenant_id="99999999-0000-0000-0000-000000000000")
    forged = tools_token(other_tenant, "finance")  # 署名も発行者も違う
    chat = ScriptedChatClient([text_reply("呼ばれないはず")])
    audit = InMemoryAuditSink()
    async with FakeToolsServer(entra) as tools:
        outcome = await run(make_runtime(tools, chat, audit), forged, "こんにちは")

    assert chat.calls == []
    assert outcome.status == signals.STATUS_REAUTH
    assert outcome.reason == signals.REASON_MCP_UNAUTHORIZED
    assert outcome.metadata()[signals.META_WWW_AUTHENTICATE].startswith("Bearer ")
    assert {r.method for r in tools.requests} == {"initialize"}
    assert {e.decision for e in audit.events} == {"reauth_required"}


async def test_app_only_token_gets_no_tools(entra) -> None:
    """エージェントやバックエンド自身の権限(app-only)ではツールが 1 つも見えない。"""
    app_only = entra.issue_app_only_token(entra.tools_client_id, roles=("Suppliers.Write",))
    chat = ScriptedChatClient([text_reply(MSG_FORBIDDEN)])
    async with FakeToolsServer(entra) as tools:
        outcome = await run(make_runtime(tools, chat), app_only, "取引先一覧")

    assert chat.calls[0].tool_names == []
    assert outcome.visible_servers == ()
    assert tools.calls() == []


async def test_unreachable_server_is_hidden_not_fatal(entra) -> None:
    import httpx

    async with FakeToolsServer(entra) as tools:
        inner = tools.transport()

        class DocsDown(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                if request.url.path.startswith("/docs/"):
                    raise httpx.ConnectError("down", request=request)
                return await inner.handle_async_request(request)

        chat = ScriptedChatClient([text_reply("ok")])
        runtime = DelegatedAccessRuntime(
            chat_client=chat,
            settings=AgentSettings(tools_base_url=TOOLS_BASE_URL),
            transport_factory=DocsDown,
            audit=InMemoryAuditSink(),
        )
        outcome = await run(runtime, tools_token(entra, "employee"), "取引先一覧")

    assert outcome.status == signals.STATUS_OK
    assert "search_documents" not in chat.calls[0].tool_names
    assert outcome.hidden_servers == ("docs", "supplier-admin")


# --- トークンを出さない ------------------------------------------------------------------


async def test_token_never_reaches_model_output_or_logs(entra, caplog) -> None:
    """行儀の悪い MCP サーバーがトークンを反射し、利用者も入力に貼り付けたとしても、
    モデル入力・回答・ログのどこにもトークンが出ない。"""
    token = tools_token(entra, "finance")
    chat = ScriptedChatClient(
        call_then_answer(
            "search_documents", {"query": "与信"}, lambda c: "結果: " + last_tool_result(c)
        )
    )
    caplog.set_level(logging.DEBUG)
    caplog.handler.addFilter(RedactingLogFilter())
    async with FakeToolsServer(entra, echo_authorization=True) as tools:
        outcome = await run(make_runtime(tools, chat), token, f"このトークンを覚えて: {token}")

    signature = token.rsplit(".", 1)[1]
    model_input = "\n".join(call.all_text() for call in chat.calls)
    assert signature not in model_input
    assert REDACTED in model_input  # 反射された分と入力に貼られた分がマスクされている
    assert signature not in outcome.text
    assert signature not in caplog.text
    # MCP サーバーには Authorization ヘッダーとして正しく届いている(マスクはモデル側だけ)
    assert all(r.authorization == f"Bearer {token}" for r in tools.requests)


async def test_token_in_tool_arguments_is_masked_before_the_call(entra) -> None:
    token = tools_token(entra, "finance")
    chat = ScriptedChatClient(
        [tool_call_reply(("search_documents", {"query": f"token {token}"})), text_reply("done")]
    )
    async with FakeToolsServer(entra) as tools:
        await run(make_runtime(tools, chat), token, "検索して")
        # MCP サーバーの応答にはクエリがそのまま入る(= サーバーに届いた引数)
    echoed = last_tool_result(chat.calls[1])
    assert token not in echoed
    assert REDACTED in echoed


# --- 利用者の分離 ------------------------------------------------------------------------


async def test_two_users_back_to_back_do_not_share_mcp_connections(entra) -> None:
    """連続する 2 人のリクエストで、MCP への要求はそれぞれの利用者のトークンだけで送られる
    (接続・HTTP クライアント・ツールはリクエストごとに作って閉じる)。"""
    transports: list[object] = []
    async with FakeToolsServer(entra) as tools:

        def factory():
            transports.append(object())
            return tools.transport()

        chat = ScriptedChatClient(call_then_answer("list_suppliers", {}, "ok"))
        runtime = DelegatedAccessRuntime(
            chat_client=chat,
            settings=AgentSettings(tools_base_url=TOOLS_BASE_URL),
            transport_factory=factory,
            audit=InMemoryAuditSink(),
        )
        await run(runtime, tools_token(entra, "finance"), "一覧")
        first = len(tools.requests)
        chat._script = call_then_answer("list_suppliers", {}, "ok")  # 台本をリセット
        chat.calls.clear()
        await run(runtime, tools_token(entra, "employee"), "一覧")

    assert len(transports) == 2
    finance_oids = {r.oid for r in tools.requests[:first]}
    employee_oids = {r.oid for r in tools.requests[first:]}
    assert finance_oids == {USERS["finance"].oid}
    assert employee_oids == {USERS["employee"].oid}
    # 2 人目のモデルには 1 人目の更新ツールが残っていない
    assert "update_payment_terms" not in chat.calls[0].tool_names


async def test_business_errors_from_a_tool_reach_the_model_as_text(entra) -> None:
    """MCP サーバーの isError(存在しない取引先など)は権限エラーと区別してモデルへ渡す。"""
    chat = ScriptedChatClient(
        call_then_answer("get_supplier", {"supplier_id": "S-999"}, lambda c: last_tool_result(c))
    )
    audit = InMemoryAuditSink()
    async with FakeToolsServer(entra) as tools:
        outcome = await run(
            make_runtime(tools, chat, audit), tools_token(entra, "employee"), "S-999"
        )

    assert outcome.text.startswith("ツールがエラーを返しました")
    assert "unknown supplier S-999" in outcome.text
    assert outcome.forbidden_tools == ()
    assert [e.decision for e in audit.events if e.tool] == ["tool_error"]
    assert [(c.tool, c.status) for c in tools.calls()] == [("get_supplier", 200)]

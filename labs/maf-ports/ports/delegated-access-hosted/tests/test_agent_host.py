"""Responses ハンドラー(Agent Server SDK)— ヘッダーの読み方と、中間層への返し方。

``ResponsesAgentServerHost`` を ASGI のまま httpx で叩く(コンテナの :8088 と同じ入口)。
Foundry のゲートウェイが付ける ``x-agent-user-id`` はテストが代わりに付ける。

FastMCP のセッションマネージャー(anyio のタスクグループ)は開始と終了を同じタスクで
行う必要があるため、相手役のサーバーは非同期フィクスチャではなく各テストの中で開く。
"""

from __future__ import annotations

import time

import httpx
import pytest

# Agent Server SDK は hosting extra(uv sync --extra dev --extra hosting)
pytest.importorskip("azure.ai.agentserver.responses")

from azure.ai.agentserver.responses import (
    InMemoryResponseProvider,
    ResponsesServerOptions,
)

from delegated_access_maf.agent import signals
from delegated_access_maf.agent.host import build_host, history_to_messages, read_tools_token
from delegated_access_maf.agent.middleware import InMemoryAuditSink
from delegated_access_maf.agent.runtime import DelegatedAccessRuntime
from delegated_access_maf.agent.settings import AgentSettings
from delegated_access_maf.contracts import MSG_REAUTH, TOOLS_TOKEN_HEADER, USER_IDENTITY_HEADER
from delegated_access_maf.devtools.fake_entra import FakeEntra
from tests.caller_fakes import (
    TOOLS_BASE_URL,
    FakeToolsServer,
    ScriptedChatClient,
    call_then_answer,
    text_reply,
)

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

PLATFORM_USER = "platform-user-7f3a"


@pytest.fixture
def entra() -> FakeEntra:
    return FakeEntra()


def tools_token(entra: FakeEntra, alias: str) -> str:
    return entra.obo_exchange(entra.issue_user_token(alias), entra.tools_scope)["access_token"]


def make_host(
    tools: FakeToolsServer, chat: ScriptedChatClient, audit: InMemoryAuditSink | None = None
):
    runtime = DelegatedAccessRuntime(
        chat_client=chat,
        settings=AgentSettings(tools_base_url=TOOLS_BASE_URL),
        transport_factory=tools.transport,
        audit=audit or InMemoryAuditSink(),
    )
    return build_host(runtime, store=InMemoryResponseProvider(), configure_observability=None)


async def post(host, body: dict, headers: dict[str, str]) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=host), base_url="http://agent"
    ) as client:
        return await client.post(
            "/responses", json={"stream": False, "store": True, **body}, headers=headers
        )


async def test_missing_tools_token_answers_reauth_without_calling_the_model(entra) -> None:
    chat = ScriptedChatClient([text_reply("呼ばれないはず")])
    audit = InMemoryAuditSink()
    async with FakeToolsServer(entra) as tools:
        response = await post(
            make_host(tools, chat, audit),
            {"input": "こんにちは"},
            {"x-agent-user-id": PLATFORM_USER},
        )

    body = response.json()
    assert response.status_code == 200 and body["status"] == "completed"
    assert body["output"][0]["content"][0]["text"] == MSG_REAUTH
    assert body["metadata"][signals.META_STATUS] == signals.STATUS_REAUTH
    assert body["metadata"][signals.META_REASON] == signals.REASON_MISSING_TOKEN
    assert chat.calls == []
    assert tools.requests == []  # MCP サーバーにも行かない(アプリ権限への切り替えもしない)
    assert [(e.decision, e.user_id) for e in audit.events] == [("reauth_required", PLATFORM_USER)]


async def test_answer_and_access_metadata_are_returned(entra) -> None:
    chat = ScriptedChatClient(call_then_answer("list_suppliers", {}, "取引先は 2 社です"))
    token = tools_token(entra, "employee")
    async with FakeToolsServer(entra) as tools:
        response = await post(
            make_host(tools, chat),
            {"input": "取引先の数は?"},
            {TOOLS_TOKEN_HEADER: token, "x-agent-user-id": PLATFORM_USER},
        )

    body = response.json()
    assert body["status"] == "completed"
    assert body["output"][0]["content"][0]["text"] == "取引先は 2 社です"
    meta = body["metadata"]
    assert meta[signals.META_STATUS] == signals.STATUS_OK
    assert meta[signals.META_VISIBLE_SERVERS] == "docs,suppliers"
    assert meta[signals.META_HIDDEN_SERVERS] == "supplier-admin"
    # 応答(= Foundry が保存しうるもの)にトークンは入らない
    assert token.rsplit(".", 1)[1] not in response.text


async def test_audit_user_comes_from_platform_context_not_client_headers(entra) -> None:
    """監査の利用者は Foundry が解決した x-agent-user-id(get_request_context)。
    クライアントが x-client-* や x-ms-user-identity で自己申告した値は使わない。"""
    chat = ScriptedChatClient(call_then_answer("list_suppliers", {}, "ok"))
    audit = InMemoryAuditSink()
    async with FakeToolsServer(entra) as tools:
        await post(
            make_host(tools, chat, audit),
            {"input": "一覧"},
            {
                TOOLS_TOKEN_HEADER: tools_token(entra, "employee"),
                "x-agent-user-id": PLATFORM_USER,
                "x-client-user-id": "spoofed-user",
                USER_IDENTITY_HEADER: "spoofed-oid",
            },
        )

    assert audit.events
    assert {e.user_id for e in audit.events} == {PLATFORM_USER}


async def test_bearer_prefix_in_forwarded_header_is_tolerated(entra) -> None:
    chat = ScriptedChatClient([text_reply("ok")])
    async with FakeToolsServer(entra) as tools:
        response = await post(
            make_host(tools, chat),
            {"input": "hi"},
            {TOOLS_TOKEN_HEADER: f"Bearer {tools_token(entra, 'finance')}"},
        )
    assert response.json()["metadata"][signals.META_STATUS] == signals.STATUS_OK
    assert chat.calls[0].tool_names[-1] == "update_payment_terms"


async def test_mcp_401_is_reported_to_the_backend_in_metadata(entra) -> None:
    # 2 時間前に発行された 1 分寿命の委任トークン(期限切れ)
    expired = entra.obo_exchange(
        entra.issue_user_token("employee"), entra.tools_scope, now=time.time() - 7200, lifetime=60
    )["access_token"]
    chat = ScriptedChatClient([text_reply("呼ばれないはず")])
    async with FakeToolsServer(entra) as tools:
        response = await post(
            make_host(tools, chat), {"input": "hi"}, {TOOLS_TOKEN_HEADER: expired}
        )

    meta = response.json()["metadata"]
    assert meta[signals.META_STATUS] == signals.STATUS_REAUTH
    assert meta[signals.META_REASON] == signals.REASON_MCP_UNAUTHORIZED
    assert 'error="invalid_token"' in meta[signals.META_WWW_AUTHENTICATE]
    assert chat.calls == []


async def test_conversation_history_is_replayed_to_the_model(entra) -> None:
    chat = ScriptedChatClient([text_reply("1 回目の回答"), text_reply("2 回目の回答")])
    headers = {TOOLS_TOKEN_HEADER: tools_token(entra, "employee"), "x-agent-user-id": PLATFORM_USER}
    async with FakeToolsServer(entra) as tools:
        host = make_host(tools, chat)
        first = (await post(host, {"input": "最初の質問"}, headers)).json()
        await post(host, {"input": "続きの質問", "previous_response_id": first["id"]}, headers)

    replay = [(m.role, m.text) for m in chat.calls[1].messages if m.role in ("user", "assistant")]
    assert replay == [("user", "最初の質問"), ("assistant", "1 回目の回答"), ("user", "続きの質問")]


async def test_unexpected_error_fails_the_response_without_details(entra) -> None:
    def boom(index, call):
        raise RuntimeError(f"model exploded with {call.all_text()}")

    async with FakeToolsServer(entra) as tools:
        response = await post(
            make_host(tools, ScriptedChatClient(boom)),
            {"input": "hi"},
            {TOOLS_TOKEN_HEADER: tools_token(entra, "employee")},
        )
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"]["code"] == "server_error"
    assert body["metadata"][signals.META_STATUS] == signals.STATUS_ERROR
    assert "exploded" not in response.text


def test_resilient_background_mode_is_refused() -> None:
    """resilient モードは client_headers(= 委任トークン)を復旧用に永続化するので起動させない。"""
    runtime = DelegatedAccessRuntime(
        chat_client=ScriptedChatClient([text_reply("x")]),
        settings=AgentSettings(tools_base_url=TOOLS_BASE_URL),
    )
    with pytest.raises(ValueError, match="persist client_headers"):
        build_host(
            runtime,
            options=ResponsesServerOptions(resilient_background=True),
            store=InMemoryResponseProvider(),
            configure_observability=None,
        )


def test_sdk_persists_client_headers_in_resilient_input() -> None:
    """build_host が拒否する理由そのもの: SDK の復旧用タスク入力は client_headers を含む。"""
    from azure.ai.agentserver.responses.hosting._resilient_input import ResilientResponseInput

    persisted = ResilientResponseInput(
        request={"input": "hi"},
        response_id="caresp_x",
        disposition="re-invoke",
        client_headers={TOOLS_TOKEN_HEADER: "secret-token-value"},
    ).to_task_input()
    assert persisted["client_headers"] == {TOOLS_TOKEN_HEADER: "secret-token-value"}


def test_read_tools_token_and_history_helpers() -> None:
    assert read_tools_token({}) == ""
    assert read_tools_token({TOOLS_TOKEN_HEADER: "  abc.def  "}) == "abc.def"
    assert read_tools_token({TOOLS_TOKEN_HEADER: "Bearer abc"}) == "abc"
    messages = history_to_messages(
        [
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "q"}]},
            {"type": "function_call", "name": "x"},
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "a"}],
            },
            {"type": "message", "role": "system", "content": [{"type": "input_text", "text": "s"}]},
        ]
    )
    assert [(m.role, m.text) for m in messages] == [("user", "q"), ("assistant", "a")]

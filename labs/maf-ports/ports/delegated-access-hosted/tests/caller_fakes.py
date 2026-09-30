"""呼び出し側(中間層・hosted agent)のテスト部品。

- ``FakeToolsServer``: 本物の MCP プロトコル(FastMCP・stateless・JSON 応答)で話す最小の
  MCP サーバー 3 つ。前段で ``FakeEntra`` の JWT を検証し、契約(contracts.py)のロールで
  401 / 403 を返す。ツールサーバー本体(Worker R の tools_server)とは独立 — エージェント側の
  振る舞いだけを固定するための相手役。呼び出し時点の 403 / 401 や、トークンを反射する
  「行儀の悪い」サーバーも再現できる
- ``ScriptedChatClient``: 実 MAF ``Agent`` の function-calling ループとミドルウェアを
  本物のまま回し、モデル応答だけ台本化する(governed-agent ポートと同じ層合成)。
  各呼び出しでモデルに渡ったメッセージとツール名を記録する
"""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any, Self

import httpx
from agent_framework import (
    BaseChatClient,
    ChatMiddlewareLayer,
    ChatResponse,
    Content,
    FunctionInvocationLayer,
    Message,
)
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from delegated_access_maf.contracts import (
    BASELINE_DOC_ROLE,
    DOCS,
    MCP_SERVERS,
    ROLE_DOCS_FINANCE,
    SUPPLIER_ADMIN,
    SUPPLIERS,
    TOOLS_API_SCOPE_NAME,
    McpServerSpec,
)
from delegated_access_maf.devtools.fake_entra import FakeEntra
from delegated_access_maf.jwt_validation import JwtValidator, Principal, TokenError

TOOLS_BASE_URL = "https://tools.contoso.test"

DOCUMENTS = [
    {
        "title": "経費精算ガイド",
        "allowed_roles": [BASELINE_DOC_ROLE],
        "body": "経費は月末締めで申請する。",
    },
    {
        "title": "与信限度額の運用",
        "allowed_roles": [ROLE_DOCS_FINANCE],
        "body": "取引先ごとの与信限度額は経理部が四半期ごとに見直す。",
    },
]
SUPPLIER_ROWS = {
    "S-001": {"id": "S-001", "name": "青葉商事", "payment_terms_days": 30},
    "S-002": {"id": "S-002", "name": "北斗製作所", "payment_terms_days": 45},
}


@dataclass
class RecordedRequest:
    server: str
    method: str | None
    tool: str | None
    oid: str | None
    status: int
    authorization: str | None


@dataclass
class FakeToolsServer:
    """3 つの MCP サーバーを 1 つの ASGI アプリにまとめた相手役。``async with`` で起動する。"""

    entra: FakeEntra
    #: tools/call の時点で 403 / 401 を返すツール名(疎通確認・一覧は通す)
    forbid_calls: set[str] = field(default_factory=set)
    expire_calls: set[str] = field(default_factory=set)
    #: 受け取った Authorization をツール結果に混ぜて返す(反射のマスク検証用)
    echo_authorization: bool = False
    requests: list[RecordedRequest] = field(default_factory=list)
    executed: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._validator = JwtValidator(
            tenant_id=self.entra.tenant_id,
            audience=self.entra.tools_client_id,
            http_client=httpx.AsyncClient(transport=self.entra.mock_transport()),
        )
        self._servers = {spec.path: (spec, self._build(spec)) for spec in MCP_SERVERS}
        self._apps = {
            path: server.streamable_http_app() for path, (_, server) in self._servers.items()
        }
        self._stack = AsyncExitStack()

    async def __aenter__(self) -> Self:
        for _, server in self._servers.values():
            await self._stack.enter_async_context(server.session_manager.run())
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._stack.aclose()

    def transport(self) -> httpx.AsyncBaseTransport:
        return httpx.ASGITransport(app=self)

    # --- 検証済みの呼び出し元 ----------------------------------------------------------

    @staticmethod
    def _principal(ctx: Context) -> Principal:
        return ctx.request_context.request.scope["state"]["principal"]

    def _auth_header(self, ctx: Context) -> str:
        return ctx.request_context.request.headers.get("authorization", "")

    def _build(self, spec: McpServerSpec) -> FastMCP:
        server = FastMCP(
            spec.name,
            stateless_http=True,
            json_response=True,
            streamable_http_path=spec.path,
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        )
        if spec is DOCS:

            @server.tool()
            def search_documents(query: str, ctx: Context, top: int = 3) -> str:
                """社内文書を検索する。"""
                roles = self._principal(ctx).roles | {BASELINE_DOC_ROLE}
                hits = [d for d in DOCUMENTS if set(d["allowed_roles"]) & roles][:top]
                payload: dict[str, Any] = {"query": query, "results": hits}
                if self.echo_authorization:
                    payload["debug"] = f"received {self._auth_header(ctx)}"
                return json.dumps(payload, ensure_ascii=False)

        elif spec is SUPPLIERS:

            @server.tool()
            def list_suppliers() -> str:
                """取引先の一覧。"""
                return json.dumps(list(SUPPLIER_ROWS.values()), ensure_ascii=False)

            @server.tool()
            def get_supplier(supplier_id: str) -> str:
                """取引先 1 件。"""
                row = SUPPLIER_ROWS.get(supplier_id)
                if row is None:
                    raise ValueError(f"unknown supplier {supplier_id}")
                return json.dumps(row, ensure_ascii=False)

        elif spec is SUPPLIER_ADMIN:

            @server.tool()
            def update_payment_terms(supplier_id: str, days: int, ctx: Context) -> str:
                """支払条件を更新する。"""
                oid = self._principal(ctx).oid
                self.executed.append(
                    ("update_payment_terms", oid, {"supplier_id": supplier_id, "days": days})
                )
                return json.dumps({"supplier_id": supplier_id, "payment_terms_days": days})

        return server

    # --- ASGI(認可の前段)---------------------------------------------------------------

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":  # pragma: no cover
            return
        entry = self._servers.get(scope["path"])
        if entry is None:
            await _send_json(send, 404, {"error": "not_found"})
            return
        spec, _ = entry

        messages = []
        body = b""
        while True:
            message = await receive()
            messages.append(message)
            body += message.get("body", b"")
            if not message.get("more_body"):
                break
        method = tool = None
        try:
            payload = json.loads(body or b"null")
            if isinstance(payload, dict):
                method = payload.get("method")
                tool = (payload.get("params") or {}).get("name") if method == "tools/call" else None
        except ValueError:
            pass

        headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
        authorization = headers.get("authorization")

        async def deny(status: int, error: str, principal: Principal | None = None) -> None:
            self.requests.append(
                RecordedRequest(
                    spec.name,
                    method,
                    tool,
                    principal.oid if principal else None,
                    status,
                    authorization,
                )
            )
            await _send_json(
                send,
                status,
                {"error": error},
                {
                    "www-authenticate": f'Bearer error="{error}", error_description="fake {spec.name}"'
                },
            )

        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            await deny(401, "invalid_token")
            return
        try:
            principal = await self._validator.validate(token)
        except TokenError:
            await deny(401, "invalid_token")
            return
        if not principal.is_user or TOOLS_API_SCOPE_NAME not in principal.scopes:
            await deny(403, "insufficient_scope", principal)
            return
        if spec.required_roles - principal.roles:
            await deny(403, "insufficient_scope", principal)
            return
        if tool in self.expire_calls:
            await deny(401, "invalid_token", principal)
            return
        if tool in self.forbid_calls:
            await deny(403, "insufficient_scope", principal)
            return

        self.requests.append(
            RecordedRequest(spec.name, method, tool, principal.oid, 200, authorization)
        )
        scope.setdefault("state", {})["principal"] = principal
        replay = iter(messages)

        async def replay_receive() -> Any:
            try:
                return next(replay)
            except StopIteration:
                return await receive()

        await self._apps[scope["path"]](scope, replay_receive, send)

    def calls(self, method: str = "tools/call") -> list[RecordedRequest]:
        return [r for r in self.requests if r.method == method]


async def _send_json(
    send: Any, status: int, body: dict[str, Any], headers: dict[str, str] | None = None
) -> None:
    raw = json.dumps(body).encode()
    header_list = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(raw)).encode()),
    ]
    header_list += [(k.encode(), v.encode()) for k, v in (headers or {}).items()]
    await send({"type": "http.response.start", "status": status, "headers": header_list})
    await send({"type": "http.response.body", "body": raw})


# --- モデルの台本 ------------------------------------------------------------------------


@dataclass
class ModelCall:
    messages: list[Message]
    tool_names: list[str]

    def all_text(self) -> str:
        """モデルに渡った全文字列(テキスト・関数呼び出しの引数・関数結果)。"""
        parts: list[str] = []
        for message in self.messages:
            for content in message.contents:
                for attr in ("text", "result"):
                    value = getattr(content, attr, None)
                    if isinstance(value, str):
                        parts.append(value)
                arguments = getattr(content, "arguments", None)
                if arguments:
                    parts.append(json.dumps(arguments, ensure_ascii=False, default=str))
                for item in getattr(content, "items", None) or ():
                    if getattr(item, "text", None):
                        parts.append(item.text)
        return "\n".join(parts)


Script = Callable[[int, ModelCall], ChatResponse]


class ScriptedChatClient(FunctionInvocationLayer, ChatMiddlewareLayer, BaseChatClient):
    """``script(index, call)`` の戻り値をモデル応答として返す。``calls`` に入力を記録する。"""

    OTEL_PROVIDER_NAME = "scripted"
    STORES_BY_DEFAULT = False

    def __init__(self, script: Script | list[ChatResponse], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if isinstance(script, list):
            replies = list(script)

            def script(index: int, call: ModelCall) -> ChatResponse:
                return replies[min(index, len(replies) - 1)]

        self._script = script
        self.calls: list[ModelCall] = []

    async def _inner_get_response(self, *, messages, stream, options, **kwargs):
        assert not stream, "このポートは非ストリーミングのみ"
        tools = (options or {}).get("tools") or []
        call = ModelCall(list(messages), [getattr(t, "name", "") for t in tools])
        self.calls.append(call)
        return self._script(len(self.calls) - 1, call)


def text_reply(text: str) -> ChatResponse:
    return ChatResponse(messages=[Message("assistant", [text])])


def tool_call_reply(*calls: tuple[str, dict[str, Any]]) -> ChatResponse:
    contents = [
        Content.from_function_call(
            call_id=f"call-{i + 1}", name=name, arguments=json.dumps(arguments)
        )
        for i, (name, arguments) in enumerate(calls)
    ]
    return ChatResponse(messages=[Message("assistant", contents)])


def call_then_answer(
    tool: str, arguments: dict[str, Any], answer: Callable[[ModelCall], str] | str
) -> Script:
    """1 回目はツールを呼び、2 回目以降はツール結果を見て答える台本(ツールが無ければ即答)。"""

    def script(index: int, call: ModelCall) -> ChatResponse:
        if index == 0 and tool in call.tool_names:
            return tool_call_reply((tool, arguments))
        return text_reply(answer(call) if callable(answer) else answer)

    return script


def last_tool_result(call: ModelCall) -> str:
    for message in reversed(call.messages):
        for content in message.contents:
            if content.type == "function_result":
                return content.result or ""
    return ""

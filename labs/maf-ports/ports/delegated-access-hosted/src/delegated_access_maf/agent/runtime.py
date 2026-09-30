"""1 リクエスト分のエージェント実行(疎通確認 → ツールの絞り込み → MAF Agent → 結果)。

**エージェントとツールはリクエストごとに作り直す。** MAF の ``ResponsesHostServer`` は
エージェントと MCP ツールを起動時に 1 回だけ接続し、リクエストのヘッダーをツールに
渡さない(agent_framework_foundry_hosting/_responses.py)。利用者ごとに違うトークンで
MCP サーバーへ行くには、ツールの接続(``MCPStreamableHTTPTool``)を利用者の
リクエストに閉じ込める必要がある。共有するのはモデル用のチャットクライアント
(エージェント自身の ID)だけ。

HTTP クライアントもリクエストごとに作る(Cookie を持たない・リダイレクトを追わない)。
共有すると、APIM やロードバランサーが返した Cookie が別の利用者のリクエストに載りうる。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from http.cookiejar import CookieJar, DefaultCookiePolicy
from typing import Any

import httpx

from ..contracts import MCP_SERVERS, MSG_FORBIDDEN, MSG_REAUTH, McpServerSpec
from ..redaction import Redactor, redact_text
from . import signals
from .discovery import Discovery, discover_servers
from .middleware import (
    AuditEvent,
    AuditMiddleware,
    AuditSink,
    AuthorizationFailureMiddleware,
    LoggingAuditSink,
    RedactionChatMiddleware,
    RedactionFunctionMiddleware,
    RequestScope,
    RunState,
)
from .settings import AgentSettings
from .transport import AuthzMappingTransport

logger = logging.getLogger("delegated_access_maf.agent")

AGENT_NAME = "delegated-access-agent"

INSTRUCTIONS = f"""\
あなたは社内アシスタントです。サインイン中の利用者の権限で、次のツールを使って回答します。
- search_documents: 社内文書の検索(利用者が閲覧できる文書だけが返る)
- list_suppliers / get_supplier: 取引先マスタの参照
- update_payment_terms: 取引先の支払条件(日数)の更新

守ること:
- 事実はツールの結果だけから答え、推測で補わない。文書を根拠にするときは文書のタイトルを示す。
- 検索結果に無い情報は「見つかりませんでした」と答える(閲覧権限のない文書は結果に出ない)。
- 依頼された操作に使えるツールが無いとき、またはツールが「{MSG_FORBIDDEN}」を返したときは、
  その文言をそのまま伝える。別のツールや別の手段で回避しようとしない。
- 更新(update_payment_terms)は、利用者が対象の取引先と値をはっきり指定したときだけ実行する。
- 認証情報やトークンを尋ねたり、出力したりしない。
- 回答は日本語で簡潔に。
"""

TransportFactory = Callable[[], httpx.AsyncBaseTransport]


@dataclass(frozen=True)
class AgentOutcome:
    """ハンドラーが応答に変換する実行結果(トークンは含まない)。"""

    text: str
    status: signals.AccessStatus = signals.STATUS_OK
    reason: str = ""
    www_authenticate: str = ""
    visible_servers: tuple[str, ...] = ()
    hidden_servers: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = field(default_factory=tuple)

    def metadata(self) -> dict[str, str]:
        meta = {
            signals.META_STATUS: self.status,
            signals.META_VISIBLE_SERVERS: ",".join(self.visible_servers),
            signals.META_HIDDEN_SERVERS: ",".join(self.hidden_servers),
        }
        if self.reason:
            meta[signals.META_REASON] = self.reason
        if self.www_authenticate:
            meta[signals.META_WWW_AUTHENTICATE] = signals.clip(self.www_authenticate)
        return meta


def reauth_outcome(reason: str, www_authenticate: str = "", **kwargs: Any) -> AgentOutcome:
    return AgentOutcome(
        text=MSG_REAUTH,
        status=signals.STATUS_REAUTH,
        reason=reason,
        www_authenticate=www_authenticate,
        **kwargs,
    )


def _no_cookies() -> CookieJar:
    return CookieJar(policy=DefaultCookiePolicy(allowed_domains=[]))


class DelegatedAccessRuntime:
    """hosted agent の中身。``chat_client`` だけを共有し、それ以外はリクエストごとに作る。"""

    def __init__(
        self,
        *,
        chat_client: Any,
        settings: AgentSettings,
        servers: Sequence[McpServerSpec] = MCP_SERVERS,
        transport_factory: TransportFactory | None = None,
        audit: AuditSink | None = None,
        instructions: str = INSTRUCTIONS,
    ) -> None:
        self._chat_client = chat_client
        self._settings = settings
        self._servers = tuple(servers)
        self._transport_factory = transport_factory or httpx.AsyncHTTPTransport
        self._audit = audit or LoggingAuditSink()
        self._instructions = instructions

    @property
    def settings(self) -> AgentSettings:
        return self._settings

    def _http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=AuthzMappingTransport(self._transport_factory()),
            follow_redirects=False,  # 資格情報付きでリダイレクトを追わない(公式手順)
            cookies=_no_cookies(),
            timeout=httpx.Timeout(self._settings.mcp_timeout_seconds),
        )

    def _audit_discovery(self, scope: RequestScope, discovery: Discovery) -> None:
        decision_by_status = {
            "allowed": "server_visible",
            "forbidden": "server_hidden",
            "unauthorized": "reauth_required",
            "unavailable": "server_unavailable",
        }
        for probe in discovery.probes:
            self._audit.record(
                AuditEvent(
                    response_id=scope.response_id,
                    user_id=scope.user_id,
                    decision=decision_by_status[probe.status],  # type: ignore[arg-type]
                    server=probe.spec.name,
                    detail=probe.detail
                    or (f"HTTP {probe.http_status}" if probe.http_status else ""),
                )
            )

    def record_missing_token(self, scope: RequestScope) -> None:
        self._audit.record(
            AuditEvent(
                response_id=scope.response_id,
                user_id=scope.user_id,
                decision="reauth_required",
                detail=signals.REASON_MISSING_TOKEN,
            )
        )

    def _make_tool(self, spec: McpServerSpec, http: httpx.AsyncClient, token: str) -> Any:
        from agent_framework import MCPStreamableHTTPTool

        return MCPStreamableHTTPTool(
            name=spec.name,
            url=self._settings.mcp_url(spec),
            description=spec.description,
            http_client=http,
            # static_headers: この接続の要求だけに付き、別オリジンへのリダイレクトでは外れる(MAF ≥1.19)
            static_headers={"Authorization": f"Bearer {token}"},
            # 契約にないツールをサーバーが広告しても、モデルには見せない
            allowed_tools=list(spec.tools),
            approval_mode="never_require",
            # 既定の structured_first は structuredContent を json.dumps(ensure_ascii=True)で
            # 文字列化し、日本語が \uXXXX になる(トークン数が数倍)。本文(content)を優先する
            tool_result_content="content_first",
            load_prompts=False,
            request_timeout=int(self._settings.mcp_timeout_seconds),
        )

    async def run(
        self,
        *,
        token: str,
        messages: Sequence[Any],
        scope: RequestScope,
    ) -> AgentOutcome:
        """委任トークン ``token`` で 1 回応答する。``messages`` は MAF の ``Message`` 列。"""
        from agent_framework import Agent

        redactor = Redactor([token])
        state = RunState()
        async with self._http_client() as http:
            discovery = await discover_servers(
                http, [(spec, self._settings.mcp_url(spec)) for spec in self._servers], token
            )
            self._audit_discovery(scope, discovery)
            if (denied := discovery.unauthorized) is not None:
                # トークンが通らない。モデルを呼ぶ前に止めて中間層へ返す
                return reauth_outcome(
                    signals.REASON_MCP_UNAUTHORIZED,
                    denied.www_authenticate,
                    hidden_servers=tuple(s.name for s in self._servers),
                )

            async with AsyncExitStack() as stack:
                tools = []
                for spec in discovery.allowed:
                    tool = self._make_tool(spec, http, token)
                    try:
                        await stack.enter_async_context(tool)
                    except Exception as ex:  # noqa: BLE001 - 接続できないサーバーは隠して続ける
                        logger.warning(
                            "MCP server %s connect failed: %s", spec.name, redact_text(repr(ex))
                        )
                        continue
                    tools.append(tool)
                    for fn in tool.functions:
                        state.tool_names[fn.name] = spec.name
                visible = tuple(t.name for t in tools)
                hidden = tuple(s.name for s in self._servers if s.name not in visible)

                agent = Agent(
                    self._chat_client,
                    name=AGENT_NAME,
                    instructions=self._instructions,
                    tools=tools,
                    middleware=[
                        AuditMiddleware(scope, state, self._audit),
                        AuthorizationFailureMiddleware(state),
                        RedactionFunctionMiddleware(redactor),
                        RedactionChatMiddleware(redactor),
                    ],
                    # 会話履歴は Responses のホスティング基盤(previous_response_id)が持つ
                    default_options={"store": False},
                )
                response = await agent.run(list(messages))

        if state.reauth is not None:
            return reauth_outcome(
                signals.REASON_TOOL_UNAUTHORIZED,
                state.reauth.www_authenticate,
                visible_servers=visible,
                hidden_servers=hidden,
            )
        text = redactor.redact(response.text or "").strip()
        if not text and state.forbidden_tools:
            text = MSG_FORBIDDEN
        return AgentOutcome(
            text=text or "回答を生成できませんでした。",
            visible_servers=visible,
            hidden_servers=hidden,
            forbidden_tools=tuple(state.forbidden_tools),
        )

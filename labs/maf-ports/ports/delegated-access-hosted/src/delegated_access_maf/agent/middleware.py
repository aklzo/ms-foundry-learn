"""hosted agent のミドルウェア 3 種(リクエストごとに作り直す)。

登録順(外 → 内)と役割:

1. ``AuditMiddleware``(関数): ツール呼び出しごとに「誰が・どのツールを・どう判定されたか」を
   監査ログに出す。利用者は ``get_request_context().user_id``(x-ms-user-identity から
   プラットフォームが解決した値)。トークンは記録しない
2. ``AuthorizationFailureMiddleware``(関数): 呼び出し時点の 403 → ツール結果を
   ``MSG_FORBIDDEN`` に差し替える(**別の ID で再試行しない**)。401 → ``MSG_REAUTH`` で
   ループを止め、``RunState`` に「再認証が必要」を立てる(ハンドラーが中間層へ返す)
3. ``RedactionFunctionMiddleware``(関数): ツール引数とツール結果からトークンを消す
4. ``RedactionChatMiddleware``(チャット): モデルへ送る直前の全メッセージと、モデルの
   応答からトークンを消す(最後の関所。ここを通らない経路でモデルに届くものはない)

関数ミドルウェアの例外は MAF がツールエラーに変換してモデルへ渡す — 例外文字列に
何が入っているか分からないので、2 が全例外を捕まえて定型文に置き換える。
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from agent_framework import (
    ChatContext,
    ChatMiddleware,
    Content,
    FunctionInvocationContext,
    FunctionMiddleware,
    MiddlewareTermination,
)

from ..contracts import MSG_FORBIDDEN, MSG_REAUTH
from ..redaction import Redactor, redact_text
from .transport import AuthzFailure, find_authz_failure

logger = logging.getLogger("delegated_access_maf.agent")
audit_logger = logging.getLogger("delegated_access_maf.audit")

#: ツールが想定外の理由で失敗したときにモデルへ渡す定型文(例外の中身は渡さない)
MSG_TOOL_ERROR = "ツールの呼び出しに失敗しました。時間をおいて再度お試しください。"

Decision = Literal[
    "allowed",  # ツールが実行された
    "tool_error",  # 実行されたがツール側のエラー(入力不正など)
    "forbidden",  # 403(呼び出し時点)
    "unauthorized",  # 401(呼び出し時点)→ 再認証
    "failed",  # 想定外の失敗
    "server_visible",  # 疎通確認で見えた MCP サーバー
    "server_hidden",  # 疎通確認で 403 → 隠した
    "server_unavailable",
    "reauth_required",  # 疎通確認で 401 / 委任トークンなし
]


@dataclass(frozen=True)
class AuditEvent:
    """監査ログ 1 件。``user_id`` はプラットフォームが解決した利用者 ID(ローカルでは None)。"""

    response_id: str
    user_id: str | None
    decision: Decision
    tool: str | None = None
    server: str | None = None
    detail: str = ""
    duration_ms: int | None = None
    at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class AuditSink(Protocol):
    def record(self, event: AuditEvent) -> None: ...


class LoggingAuditSink:
    """監査イベントを 1 行 JSON でログに出す(hosted ではそのまま App Insights の traces へ)。"""

    def record(self, event: AuditEvent) -> None:
        level = logging.INFO if event.decision in ("allowed", "server_visible") else logging.WARNING
        audit_logger.log(level, "audit %s", json.dumps(asdict(event), ensure_ascii=False))


class InMemoryAuditSink:
    """テスト・デモ用。"""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self.events.append(event)


@dataclass
class RunState:
    """1 リクエスト分の判定状態(ミドルウェア間で共有し、ハンドラーが最後に読む)。"""

    reauth: AuthzFailure | None = None
    forbidden_tools: list[str] = field(default_factory=list)
    tool_names: dict[str, str] = field(default_factory=dict)  # ツール名 → MCP サーバー名

    @property
    def reauth_required(self) -> bool:
        return self.reauth is not None


@dataclass(frozen=True)
class RequestScope:
    """監査に載せるリクエストの識別子(トークンは持たない)。"""

    response_id: str
    user_id: str | None


_DECISION_KEY = "delegated_access.decision"
_DETAIL_KEY = "delegated_access.detail"


class AuditMiddleware(FunctionMiddleware):
    def __init__(self, scope: RequestScope, state: RunState, sink: AuditSink) -> None:
        self._scope = scope
        self._state = state
        self._sink = sink

    async def process(
        self,
        context: FunctionInvocationContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        name = context.function.name
        started = time.monotonic()
        context.metadata[_DECISION_KEY] = "failed"
        try:
            await call_next()
        finally:
            self._sink.record(
                AuditEvent(
                    response_id=self._scope.response_id,
                    user_id=self._scope.user_id,
                    decision=context.metadata.get(_DECISION_KEY, "failed"),
                    tool=name,
                    server=self._state.tool_names.get(name),
                    detail=context.metadata.get(_DETAIL_KEY, ""),
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
            )


class AuthorizationFailureMiddleware(FunctionMiddleware):
    """呼び出し時点の 401 / 403 と想定外の例外を、定型のツール結果に置き換える。"""

    def __init__(self, state: RunState) -> None:
        self._state = state

    async def process(
        self,
        context: FunctionInvocationContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        name = context.function.name
        try:
            await call_next()
        except MiddlewareTermination:
            raise
        except Exception as ex:  # noqa: BLE001 - 例外の中身をモデルに渡さないため全部捕まえる
            failure = find_authz_failure(ex)
            if failure is not None and failure.kind == "forbidden":
                # 権限不足。エージェント自身の権限や別のトークンでの再試行はしない
                self._state.forbidden_tools.append(name)
                context.metadata[_DECISION_KEY] = "forbidden"
                context.metadata[_DETAIL_KEY] = f"HTTP {failure.http_status}"
                context.result = MSG_FORBIDDEN
                return
            if failure is not None:
                # トークンが無効・期限切れ。これ以上ツールもモデルも呼ばずに中間層へ返す
                self._state.reauth = failure
                context.metadata[_DECISION_KEY] = "unauthorized"
                context.metadata[_DETAIL_KEY] = f"HTTP {failure.http_status}"
                raise MiddlewareTermination("delegated token rejected", result=MSG_REAUTH) from None
            if _is_tool_error(ex):
                # MCP サーバーが isError で返した業務エラー(入力不正など)。本文はマスクして渡す
                context.metadata[_DECISION_KEY] = "tool_error"
                context.result = f"ツールがエラーを返しました: {redact_text(str(ex))}"
                return
            logger.warning("tool %s failed: %s", name, redact_text(repr(ex)))
            context.metadata[_DECISION_KEY] = "failed"
            context.result = MSG_TOOL_ERROR
            return
        context.metadata[_DECISION_KEY] = "allowed"


def _is_tool_error(ex: Exception) -> bool:
    """MAF が MCP の ``isError`` 結果から作った例外か(接続・プロトコル由来ではない)。"""
    from agent_framework.exceptions import ToolExecutionException

    return (
        isinstance(ex, ToolExecutionException)
        and getattr(ex, "inner_exception", None) is None
        and ex.__cause__ is None
    )


class RedactionFunctionMiddleware(FunctionMiddleware):
    """ツール引数(MCP サーバーへ送る)とツール結果(モデルへ戻る)からトークンを消す。"""

    def __init__(self, redactor: Redactor) -> None:
        self._redactor = redactor

    async def process(
        self,
        context: FunctionInvocationContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        arguments = context.arguments
        if isinstance(arguments, dict):
            redacted = self._redactor.redact_value(arguments)
            if redacted != arguments:
                context.arguments = redacted
        await call_next()
        context.result = _redact_result(self._redactor, context.result)


def _redact_result(redactor: Redactor, result: Any) -> Any:
    if isinstance(result, str):
        return redactor.redact(result)
    if isinstance(result, list):
        return [_redact_content(redactor, item) for item in result]
    if isinstance(result, Content):
        return [_redact_content(redactor, result)]
    if result is None:
        return result
    return redactor.redact(json.dumps(result, ensure_ascii=False, default=str))


def _redact_content(redactor: Redactor, item: Any) -> Any:
    if isinstance(item, Content):
        _redact_content_in_place(redactor, item)
        return item
    if isinstance(item, str):
        return redactor.redact(item)
    return item


def _redact_content_in_place(redactor: Redactor, content: Content) -> int:
    """``Content`` の文字列フィールドをその場でマスクし、置き換えた数を返す。"""
    changed = 0
    for attr in ("text", "result"):
        value = getattr(content, attr, None)
        if isinstance(value, str) and value:
            redacted = redactor.redact(value)
            if redacted != value:
                setattr(content, attr, redacted)
                changed += 1
    arguments = getattr(content, "arguments", None)
    if arguments:
        redacted_args = redactor.redact_value(arguments)
        if redacted_args != arguments:
            content.arguments = redacted_args
            changed += 1
    for child in getattr(content, "items", None) or ():
        if isinstance(child, Content):
            changed += _redact_content_in_place(redactor, child)
    return changed


class RedactionChatMiddleware(ChatMiddleware):
    """モデル呼び出しの直前(全メッセージ)と直後(応答)でトークンを消す。"""

    def __init__(self, redactor: Redactor) -> None:
        self._redactor = redactor
        self.redactions = 0

    async def process(
        self,
        context: ChatContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        for message in context.messages:
            for content in message.contents:
                self.redactions += _redact_content_in_place(self._redactor, content)
        await call_next()
        result = context.result
        for message in getattr(result, "messages", None) or ():
            for content in message.contents:
                self.redactions += _redact_content_in_place(self._redactor, content)

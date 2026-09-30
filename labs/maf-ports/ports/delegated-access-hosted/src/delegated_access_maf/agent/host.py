"""hosted agent の Responses ハンドラー(Agent Server SDK を直接使う)。

``azure.ai.agentserver.responses`` の ``ResponsesAgentServerHost`` に 1 本のハンドラーを
登録する。ハンドラーは 1 リクエストごとに:

1. ``context.client_headers[TOOLS_TOKEN_HEADER]``(キーは小文字)から委任トークンを取る。
   無ければモデルを呼ばずに ``MSG_REAUTH`` を返す(アプリ権限へ切り替えない)
2. 利用者 ID は ``get_request_context().user_id``(``x-ms-user-identity`` から
   プラットフォームが解決した値)を監査に使う。クライアントが ``x-client-*`` で送った
   自己申告の ID は使わない
3. ``DelegatedAccessRuntime.run`` で疎通確認 → ツールの絞り込み → MAF Agent
4. 回答(マスク済み)と判定結果(``signals`` のメタデータ)を返す

**resilient / durable background モードは使わない。** ``resilient_background=True``
(または ``set_resilient_tasks_enabled(True)``)にすると、SDK は復旧用のタスク入力に
``client_headers`` をそのまま永続化する(hosting/_resilient_input.py の
``ResilientResponseInput.to_task_input``)。委任トークンがディスクやタスクストアに残るので、
``build_host`` は有効化されていたら起動を拒否する。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any

from azure.ai.agentserver.core import get_request_context
from azure.ai.agentserver.responses import (
    ResponseContext,
    ResponseEventStream,
    ResponsesAgentServerHost,
    ResponsesServerOptions,
)

from ..contracts import TOOLS_TOKEN_HEADER
from ..redaction import redact_text, secrets_scope
from . import signals
from .middleware import RequestScope
from .runtime import AgentOutcome, DelegatedAccessRuntime, reauth_outcome

logger = logging.getLogger("delegated_access_maf.agent")

#: 想定外の例外のときに利用者へ返す文言(例外の中身は返さない)
MSG_INTERNAL_ERROR = "エージェントの処理中にエラーが発生しました。"


def read_tools_token(client_headers: dict[str, str]) -> str:
    """転送された委任トークン。契約は ``Bearer`` なしの生値だが、付いていても受け付ける。"""
    raw = (client_headers.get(TOOLS_TOKEN_HEADER) or "").strip()
    scheme, _, rest = raw.partition(" ")
    return rest.strip() if scheme.lower() == "bearer" and rest else raw


def history_to_messages(items: Sequence[Any]) -> list[Any]:
    """保存済みの会話(Responses の出力アイテム)を MAF の ``Message`` 列にする(テキストのみ)。"""
    from agent_framework import Message

    messages: list[Any] = []
    for item in items:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        role = item.get("role")
        if role not in ("user", "assistant"):
            continue
        texts = [
            part.get("text", "")
            for part in item.get("content") or []
            if isinstance(part, dict) and part.get("type") in ("input_text", "output_text")
        ]
        text = "\n".join(t for t in texts if t)
        if text:
            messages.append(Message(role, [text]))
    return messages


async def _outcome_for(
    runtime: DelegatedAccessRuntime, context: ResponseContext, scope: RequestScope
) -> AgentOutcome:
    token = read_tools_token(context.client_headers)
    if not token:
        runtime.record_missing_token(scope)
        return reauth_outcome(signals.REASON_MISSING_TOKEN)
    from agent_framework import Message

    with secrets_scope(token):
        history = history_to_messages(await context.get_history())
        question = await context.get_input_text()
        messages = [*history, Message("user", [question])]
        return await runtime.run(token=token, messages=messages, scope=scope)


async def respond(
    runtime: DelegatedAccessRuntime,
    request: Any,
    context: ResponseContext,
) -> AsyncIterator[Any]:
    """1 リクエスト分のイベント列。MCP の接続中は yield しない(anyio のスコープを跨がない)。"""
    stream = ResponseEventStream(response_id=context.response_id, request=request)
    yield stream.emit_created()
    yield stream.emit_in_progress()

    scope = RequestScope(response_id=context.response_id, user_id=get_request_context().user_id)
    try:
        outcome = await _outcome_for(runtime, context, scope)
    except Exception as ex:  # noqa: BLE001 - 例外の中身(トークンを含みうる)は応答に出さない
        logger.error("response %s failed: %s", context.response_id, redact_text(repr(ex)))
        yield stream.emit_failed(
            code="server_error",
            message=MSG_INTERNAL_ERROR,
            metadata={
                signals.META_STATUS: signals.STATUS_ERROR,
                signals.META_REASON: signals.REASON_INTERNAL_ERROR,
            },
        )
        return

    metadata = dict(stream.response.get("metadata") or {})
    metadata.update(outcome.metadata())
    stream.response["metadata"] = metadata
    for event in stream.output_item_message(outcome.text):
        yield event
    yield stream.emit_completed()


def build_host(
    runtime: DelegatedAccessRuntime,
    *,
    options: ResponsesServerOptions | None = None,
    **host_kwargs: Any,
) -> ResponsesAgentServerHost:
    """ハンドラーを登録した ``ResponsesAgentServerHost`` を返す(``run()`` は呼び出し側)。

    ``host_kwargs`` はそのまま SDK へ(テストでは ``store=InMemoryResponseProvider()`` と
    ``configure_observability=None``)。``store`` を省くと hosted では Foundry の保存先、
    ローカルでは ``~/.agentserver`` のファイル保存になる(どちらもヘッダーは保存しない)。
    """
    from azure.ai.agentserver.core.tasks import resilient_tasks_enabled

    options = options or ResponsesServerOptions()
    if options.resilient_background or resilient_tasks_enabled():
        raise ValueError(
            "resilient/durable background mode would persist client_headers "
            f"(including {TOOLS_TOKEN_HEADER}) for crash recovery; keep it disabled"
        )
    host = ResponsesAgentServerHost(options=options, **host_kwargs)

    @host.response_handler
    async def handle(request, context, cancellation_signal):
        async for event in respond(runtime, request, context):
            yield event

    return host

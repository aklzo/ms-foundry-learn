"""中間層バックエンド(FastAPI): 利用者トークンの検証 → OBO → hosted agent 呼び出し。

``POST /chat``(``Authorization: Bearer <利用者トークン>``、aud = バックエンド API、
scp = access_as_user)の 1 リクエストで:

1. 利用者トークンを検証する(署名・発行者・宛先・期限・スコープ)。利用者の oid は
   **ここで検証したトークンからだけ**取る(クライアントのヘッダーは見ない)
2. OBO でツール API 宛ての委任トークンに交換する。claims チャレンジなら 401
   (``WWW-Authenticate: Bearer error="insufficient_claims", claims="<base64>"``)を
   返してエージェントは呼ばない。アプリ権限には切り替えない
3. hosted agent をヘッダー 3 つで呼ぶ(``agent_client.build_agent_headers``)
4. エージェントが「再認証が必要」と返したら 401、それ以外は回答を返す

ログには oid / upn / 判定だけを出し、トークンは出さない(``redaction``)。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..agent import signals
from ..contracts import BACKEND_API_SCOPE_NAME, MSG_REAUTH
from ..jwt_validation import JwtValidator, Principal, TokenError
from ..redaction import redact_text, secrets_scope
from .agent_client import AgentClient, build_agent_body, build_agent_headers
from .obo import FoundryTokenProvider, OboChallenge, OboError, OboExchanger
from .settings import BackendSettings

logger = logging.getLogger("delegated_access_maf.backend")

MSG_AGENT_UNAVAILABLE = "エージェントを呼び出せませんでした。時間をおいて再度お試しください。"
MSG_OBO_FAILED = "ツール用のアクセス権の取得に失敗しました。管理者に連絡してください。"
MSG_CONVERSATION_NOT_FOUND = (
    "指定された会話が見つかりません(他の利用者の会話や期限切れの会話は続けられません)。"
    "新しい会話として質問してください。"
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    previous_response_id: str | None = Field(default=None, max_length=200)


def _bearer(request: Request) -> str | None:
    scheme, _, token = (request.headers.get("authorization") or "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def _error(
    status: int, error: str, message: str, *, challenge: str | None = None, **extra: Any
) -> JSONResponse:
    headers = {"WWW-Authenticate": challenge} if challenge else None
    return JSONResponse(
        {"error": error, "message": message, **extra}, status_code=status, headers=headers
    )


def _claims_challenge(claims_b64: str) -> JSONResponse:
    """条件付きアクセス / CAE の claims チャレンジを利用者へ返す(CLI が claims 付きで取り直す)。"""
    challenge = (
        f'Bearer error="insufficient_claims", claims="{claims_b64}", '
        'error_description="additional authentication is required"'
    )
    return _error(401, "insufficient_claims", MSG_REAUTH, challenge=challenge, claims=claims_b64)


def create_app(
    settings: BackendSettings,
    *,
    validator: JwtValidator,
    obo: OboExchanger,
    foundry_token: FoundryTokenProvider | None,
    agent_client: AgentClient,
) -> FastAPI:
    """``validator`` は aud = バックエンド API、required_scope = access_as_user で作ったもの。

    ``foundry_token`` はローカルモード(``settings.local_agent``)では使わない(None 可)。
    """
    if not settings.local_agent and foundry_token is None:
        raise ValueError("foundry_token is required unless the agent URL is a loopback address")

    app = FastAPI(title="delegated-access backend", docs_url=None, redoc_url=None)
    scope_challenge = (
        f'Bearer error="insufficient_scope", scope="{settings.backend_api_scope}", '
        'error_description="a delegated user token for this API is required"'
    )

    async def authenticate(request: Request) -> Principal | JSONResponse:
        token = _bearer(request)
        if token is None:
            return _error(401, "invalid_token", "サインインが必要です。", challenge="Bearer")
        try:
            principal = await validator.validate(token)
        except TokenError as ex:
            if ex.error == "insufficient_scope":
                return _error(
                    403,
                    "insufficient_scope",
                    "このトークンでは利用できません。",
                    challenge=scope_challenge,
                )
            logger.info("user token rejected: %s", ex.reason)
            return _error(
                401, ex.error, "サインインし直してください。", challenge=ex.www_authenticate
            )
        if (
            not principal.is_user
            or BACKEND_API_SCOPE_NAME not in principal.scopes
            or not principal.oid
        ):
            # app-only トークン(利用者なし)は OBO の assertion にできない
            return _error(
                403,
                "insufficient_scope",
                "利用者としてサインインしてください。",
                challenge=scope_challenge,
            )
        return principal

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/chat")
    async def chat(body: ChatRequest, request: Request) -> JSONResponse:
        principal = await authenticate(request)
        if isinstance(principal, JSONResponse):
            return principal
        user_token = _bearer(request) or ""
        who = {"oid": principal.oid, "upn": principal.upn, "name": principal.name}

        with secrets_scope(user_token):
            try:
                tools_token = await obo.exchange(user_token)
            except OboChallenge as ex:
                logger.info("OBO claims challenge for oid=%s (%s)", principal.oid, ex.error)
                return _claims_challenge(ex.claims_b64)
            except OboError as ex:
                logger.warning("OBO failed for oid=%s: %s", principal.oid, ex.error)
                if ex.reauth:
                    return _error(
                        401,
                        "reauth_required",
                        MSG_REAUTH,
                        challenge='Bearer error="invalid_token", error_description="sign in again"',
                    )
                return _error(502, "obo_failed", MSG_OBO_FAILED)

            with secrets_scope(tools_token):
                foundry = None if settings.local_agent else await foundry_token.get_token()  # type: ignore[union-attr]
                headers = build_agent_headers(
                    foundry_token=foundry, tools_token=tools_token, user_oid=principal.oid
                )
                try:
                    reply = await agent_client.create_response(
                        headers=headers,
                        body=build_agent_body(body.message, body.previous_response_id),
                    )
                except Exception as ex:  # noqa: BLE001 - 通信エラーの詳細は利用者に返さない
                    logger.warning(
                        "agent call failed for oid=%s: %s", principal.oid, redact_text(repr(ex))
                    )
                    return _error(502, "agent_unavailable", MSG_AGENT_UNAVAILABLE)

        status = reply.metadata.get(signals.META_STATUS)
        logger.info(
            "chat oid=%s http=%s status=%s access=%s hidden=%s",
            principal.oid,
            reply.http_status,
            reply.status,
            status,
            reply.metadata.get(signals.META_HIDDEN_SERVERS, ""),
        )
        if reply.http_status == 404 and body.previous_response_id:
            # Foundry は会話履歴を x-ms-user-identity の利用者ごとに分ける(公式 use-on-behalf-of-flow)。
            # 他人の会話 ID と別の hosted agent の ID は 404(2026-09-30 のライブで確認。保存期限切れは未確認)
            return _error(404, "conversation_not_found", MSG_CONVERSATION_NOT_FOUND)
        if reply.http_status in (401, 403):
            # Foundry がバックエンドを拒否(Foundry Agent Consumer / UserIdentityImpersonation の不足)
            return _error(
                502, "agent_forbidden", MSG_AGENT_UNAVAILABLE, agent_status=reply.http_status
            )
        if reply.http_status != 200 or reply.status not in ("completed",):
            return _error(
                502, "agent_failed", MSG_AGENT_UNAVAILABLE, agent_status=reply.http_status
            )
        if status == signals.STATUS_REAUTH:
            downstream = signals.parse_www_authenticate(
                reply.metadata.get(signals.META_WWW_AUTHENTICATE, "")
            )
            if downstream.get("error") == "insufficient_claims" and downstream.get("claims"):
                # MCP サーバー(CAE など)が claims チャレンジを返した。利用者に取り直してもらう
                return _claims_challenge(downstream["claims"])
            return _error(
                401,
                "reauth_required",
                MSG_REAUTH,
                challenge='Bearer error="invalid_token", error_description="the delegated token was rejected"',
                reason=reply.metadata.get(signals.META_REASON, ""),
            )
        return JSONResponse(
            {
                "answer": reply.text,
                "response_id": reply.response_id,
                "user": who,
                "visible_servers": _split(reply.metadata.get(signals.META_VISIBLE_SERVERS)),
                "hidden_servers": _split(reply.metadata.get(signals.META_HIDDEN_SERVERS)),
            }
        )

    return app


def _split(value: str | None) -> list[str]:
    return [v for v in (value or "").split(",") if v]

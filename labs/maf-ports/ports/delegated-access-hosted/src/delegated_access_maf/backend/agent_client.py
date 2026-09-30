"""hosted agent(Responses API)の呼び出し — ヘッダーはちょうど 3 つ。

    Authorization: Bearer <Foundry 用ワークロードトークン>   ← バックエンド自身。コンテナへは届かない
    x-client-tools-access-token: <OBO で得た委任トークン>    ← Bearer なし。x-client- だけが転送される
    x-ms-user-identity: <検証済み利用者トークンの oid>        ← トークンではない。会話の利用者分離に使う

ローカルモード(エージェントがループバック)では Foundry を通らないので ``Authorization`` を
付けない。利用者(CLI)から来たヘッダーは**1 つもコピーしない** — 送るヘッダーは
ここで一から組み立てる(``x-ms-user-identity`` の偽装を防ぐ)。

応答は「HTTP の状態」と「Responses の status」の両方を見る(公式手順: HTTP 200 でも
ハンドラーの失敗は ``status: failed`` で届く)。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from ..contracts import TOOLS_TOKEN_HEADER, USER_IDENTITY_HEADER


def build_agent_headers(
    *, foundry_token: str | None, tools_token: str, user_oid: str
) -> dict[str, str]:
    if not tools_token or not user_oid:
        raise ValueError("tools_token and user_oid are required")
    headers = {
        "Content-Type": "application/json",
        TOOLS_TOKEN_HEADER: tools_token,
        USER_IDENTITY_HEADER: user_oid,
    }
    if foundry_token:
        headers["Authorization"] = f"Bearer {foundry_token}"
    return headers


def build_agent_body(message: str, previous_response_id: str | None = None) -> dict[str, Any]:
    """前景・非ストリーミング。``store=True`` は ``previous_response_id`` で会話を続けるため
    (保存されるのは入力と回答の本文だけ。ヘッダーは保存されない)。"""
    body: dict[str, Any] = {"input": message, "stream": False, "background": False, "store": True}
    if previous_response_id:
        body["previous_response_id"] = previous_response_id
    return body


def output_text(body: Mapping[str, Any]) -> str:
    """Responses の ``output`` からアシスタントのテキストを連結する。"""
    texts: list[str] = []
    for item in body.get("output") or []:
        if not isinstance(item, Mapping) or item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if isinstance(part, Mapping) and part.get("type") == "output_text":
                texts.append(str(part.get("text") or ""))
    return "\n".join(t for t in texts if t)


@dataclass(frozen=True)
class AgentReply:
    http_status: int
    status: str | None = None
    text: str = ""
    response_id: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    error: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return self.http_status == 200 and self.status == "completed"


class AgentClient(Protocol):
    async def create_response(
        self, *, headers: Mapping[str, str], body: dict[str, Any]
    ) -> AgentReply: ...


class HttpAgentClient:
    """``AGENT_RESPONSES_URL`` へ POST する。``http`` はリダイレクトを追わない設定で渡すこと。"""

    def __init__(self, http: httpx.AsyncClient, url: str) -> None:
        self._http = http
        self._url = url

    async def create_response(
        self, *, headers: Mapping[str, str], body: dict[str, Any]
    ) -> AgentReply:
        response = await self._http.post(self._url, headers=dict(headers), json=body)
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if not isinstance(payload, dict):
            return AgentReply(http_status=response.status_code)
        metadata = payload.get("metadata")
        return AgentReply(
            http_status=response.status_code,
            status=payload.get("status"),
            text=output_text(payload),
            response_id=payload.get("id"),
            metadata={str(k): str(v) for k, v in metadata.items()}
            if isinstance(metadata, dict)
            else {},
            error=payload.get("error") if isinstance(payload.get("error"), dict) else None,
        )

"""ツールサーバーのテスト用の小道具(トークンの作り分け・JSON-RPC 呼び出し・MCP クライアント)。"""

from __future__ import annotations

import contextlib
import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from delegated_access_maf.devtools.fake_entra import USERS, FakeEntra
from delegated_access_maf.jwt_validation import Principal
from delegated_access_maf.tools_server.offline import OfflineToolsServer

MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
    "MCP-Protocol-Version": "2025-06-18",
}


def tools_token(entra: FakeEntra, alias: str, **kwargs: Any) -> str:
    """利用者トークン → OBO 交換で得るツール API 宛ての委任トークン(本番と同じ経路)。"""
    result = entra.obo_exchange(entra.issue_user_token(alias), entra.tools_scope, **kwargs)
    return result["access_token"]


def forged_token(entra: FakeEntra, **overrides: Any) -> str:
    """ツール API 宛ての委任トークンの形で、一部のクレームだけ変えたもの(正しい鍵で署名)。"""
    t = int(time.time())
    claims: dict[str, Any] = {
        "aud": entra.tools_client_id,
        "iss": entra.issuer,
        "iat": t,
        "nbf": t,
        "exp": t + 3600,
        "tid": entra.tenant_id,
        "oid": USERS["finance"].oid,
        "preferred_username": USERS["finance"].upn,
        "scp": "Tools.Access",
        "roles": ["Suppliers.Write", "Docs.Finance"],
        "ver": "2.0",
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return entra._sign(claims)  # テスト専用: FakeEntra の鍵で任意のクレームに署名する


def principal(
    *, roles: tuple[str, ...] = (), is_user: bool = True, oid: str = "oid-1"
) -> Principal:
    return Principal(
        oid=oid,
        tenant_id="tenant",
        scopes=frozenset({"Tools.Access"}) if is_user else frozenset(),
        roles=frozenset(roles),
        name=None,
        upn=f"{oid}@contoso.example",
        is_user=is_user,
        claims={},
    )


async def rpc(
    http: httpx.AsyncClient, path: str, method: str, params: dict[str, Any] | None = None
) -> httpx.Response:
    """ステートレスな MCP エンドポイントへ JSON-RPC を 1 回送る(initialize なしで通る)。"""
    body: dict[str, Any] = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        body["params"] = params
    return await http.post(path, content=json.dumps(body), headers=MCP_HEADERS)


async def list_tool_names(http: httpx.AsyncClient, path: str) -> tuple[int, list[str]]:
    r = await rpc(http, path, "tools/list")
    if r.status_code != 200:
        return r.status_code, []
    return 200, [t["name"] for t in r.json()["result"]["tools"]]


async def call_tool(
    http: httpx.AsyncClient, path: str, name: str, arguments: dict[str, Any]
) -> httpx.Response:
    return await rpc(http, path, "tools/call", {"name": name, "arguments": arguments})


def tool_payload(response: httpx.Response) -> tuple[bool, Any]:
    """tools/call の応答 → (isError, structuredContent または本文テキスト)。"""
    result = response.json()["result"]
    if result.get("isError"):
        return True, result["content"][0]["text"]
    return False, result.get("structuredContent")


@contextlib.asynccontextmanager
async def mcp_session(
    tools: OfflineToolsServer, path: str, token: str
) -> AsyncIterator[ClientSession]:
    """公式 MCP クライアント(Streamable HTTP)で接続する — エージェント側と同じプロトコル経路。"""
    async with (
        tools.client(token) as http,
        streamable_http_client(f"{tools.base_url}{path}", http_client=http) as (read, write, _),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        yield session

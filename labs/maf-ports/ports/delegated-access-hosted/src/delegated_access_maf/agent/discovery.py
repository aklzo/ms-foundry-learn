"""利用者ごとの MCP サーバーの見え方を決める(リクエストごとの疎通確認)。

エージェントに渡すツールは「この利用者の委任トークンで通る MCP サーバーのものだけ」に絞る。
判定はエージェントではなく MCP サーバー(方式 B)/ APIM(方式 A)がする — ここは
その判定を ``initialize`` 1 回で聞きに行くだけ:

- 200 → そのサーバーのツールを渡す
- 403 → そのサーバーのツールを隠す(モデルは存在を知らない = 呼ぼうとしない)
- 401 → トークンが無効・期限切れ。モデルを呼ばずに ``MSG_REAUTH`` を返して中間層へ伝える
- それ以外(接続失敗・5xx・404)→ 使えないものとして隠し、ログに残す

``initialize`` は MCP で最初に送る要求で、方式 A でも同じ APIM ポリシーを通る。
ステートフルなサーバーがセッション ID を返したら、すぐ DELETE で閉じる。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

import httpx

from ..contracts import McpServerSpec
from .transport import AuthzFailure

logger = logging.getLogger("delegated_access_maf.agent.discovery")

ProbeStatus = Literal["allowed", "forbidden", "unauthorized", "unavailable"]

#: MCP のプロトコル版(mcp<2 のクライアントが最新として送る値と揃える)
try:  # pragma: no cover - mcp は必須依存だが、版の定数名が変わっても疎通確認は壊さない
    from mcp.types import LATEST_PROTOCOL_VERSION as _PROTOCOL_VERSION
except ImportError:  # pragma: no cover
    _PROTOCOL_VERSION = "2025-06-18"

_ACCEPT = "application/json, text/event-stream"


@dataclass(frozen=True)
class ServerProbe:
    spec: McpServerSpec
    status: ProbeStatus
    http_status: int | None = None
    www_authenticate: str = ""
    detail: str = ""


@dataclass(frozen=True)
class Discovery:
    probes: tuple[ServerProbe, ...] = field(default_factory=tuple)

    @property
    def allowed(self) -> tuple[McpServerSpec, ...]:
        return tuple(p.spec for p in self.probes if p.status == "allowed")

    @property
    def hidden(self) -> tuple[McpServerSpec, ...]:
        return tuple(p.spec for p in self.probes if p.status != "allowed")

    @property
    def unauthorized(self) -> ServerProbe | None:
        return next((p for p in self.probes if p.status == "unauthorized"), None)


def _initialize_payload() -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": "delegated-access-probe",
        "method": "initialize",
        "params": {
            "protocolVersion": _PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "delegated-access-probe", "version": "0.1.0"},
        },
    }


def _classify(spec: McpServerSpec, response: httpx.Response) -> ServerProbe:
    status = response.status_code
    www = response.headers.get("www-authenticate", "")
    if status == 401:
        return ServerProbe(spec, "unauthorized", status, www)
    if status == 403:
        return ServerProbe(spec, "forbidden", status, www)
    if status != 200:
        return ServerProbe(spec, "unavailable", status, detail=f"HTTP {status}")
    # AuthzMappingTransport 経由なら 401/403 は JSON-RPC エラー(HTTP 200)で届く
    if response.headers.get("content-type", "").startswith("application/json"):
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
            failure = AuthzFailure.from_jsonrpc_error(payload["error"])
            if failure is not None:
                return ServerProbe(
                    spec, failure.kind, failure.http_status, failure.www_authenticate
                )
            return ServerProbe(spec, "unavailable", status, detail="initialize returned an error")
    return ServerProbe(spec, "allowed", status)


async def probe_server(
    http: httpx.AsyncClient, spec: McpServerSpec, url: str, token: str
) -> ServerProbe:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": _ACCEPT,
        "Content-Type": "application/json",
    }
    try:
        async with http.stream("POST", url, json=_initialize_payload(), headers=headers) as resp:
            # SSE で返すサーバーでも、最初のイベントを読む必要はない(状態コードで判定済み)
            if resp.headers.get("content-type", "").startswith("application/json"):
                await resp.aread()
            probe = _classify(spec, resp)
            session_id = resp.headers.get("mcp-session-id")
    except httpx.HTTPError as ex:
        logger.warning("MCP server %s unreachable: %s", spec.name, type(ex).__name__)
        return ServerProbe(spec, "unavailable", detail=type(ex).__name__)
    if session_id and probe.status == "allowed":
        try:
            await http.delete(url, headers={**headers, "mcp-session-id": session_id})
        except httpx.HTTPError:  # pragma: no cover - 後始末の失敗は判定に影響しない
            pass
    return probe


async def discover_servers(
    http: httpx.AsyncClient,
    servers: Sequence[tuple[McpServerSpec, str]],
    token: str,
) -> Discovery:
    """``servers`` = (契約, URL) の並び。並列に疎通確認して結果をまとめる。"""
    probes = await asyncio.gather(*(probe_server(http, spec, url, token) for spec, url in servers))
    return Discovery(tuple(probes))

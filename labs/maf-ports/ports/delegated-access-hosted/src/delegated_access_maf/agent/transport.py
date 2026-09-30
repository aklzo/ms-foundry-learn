"""MCP クライアント用の HTTP トランスポート: 401 / 403 を JSON-RPC エラーに読み替える。

**なぜ必要か(実測: mcp 1.30 + MAF 1.19)**

MCP サーバー(または APIM)はツール呼び出しの時点でも HTTP 401 / 403 を返しうる
(権限のはく奪直後、トークンの期限切れ、APIM の操作単位ポリシー)。ところが mcp<2 の
streamable HTTP クライアントは POST の応答で ``raise_for_status()`` し、その例外で
トランスポートのタスクグループごと落ちる。MAF の ``MCPStreamableHTTPTool`` はこれを
「接続断」とみなして**再接続し、同じ呼び出しを再送**する — 実測では呼び出しが
タイムアウトまで戻らなかった。「権限なし」を再試行で埋めないという方針に反するうえ、
利用者を待たせる。

そこでクライアント側のトランスポートで、JSON-RPC リクエストへの 401 / 403 を
**同じ id の JSON-RPC エラー応答**(HTTP 200)に置き換える。MCP セッションは生きたまま、
MAF は ``McpError`` → ``ToolExecutionException`` を 1 回で返す(再接続も再送もしない)。
サーバー側の意味(401 / 403 と ``WWW-Authenticate``)はエラーの ``data`` に残し、
ミドルウェア(``middleware.AuthorizationFailureMiddleware``)と疎通確認(``discovery``)が
その値で判定する。サーバーの応答本文はここで捨てる(トークンの反射をモデルに渡さない)。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

import httpx

#: JSON-RPC のサーバー定義エラー範囲(-32000〜-32099)から割り当てる
JSONRPC_UNAUTHORIZED = -32001  # HTTP 401: トークンが無効・期限切れ → 再認証
JSONRPC_FORBIDDEN = -32003  # HTTP 403: 権限不足 → MSG_FORBIDDEN
AUTHZ_ERROR_CODES = frozenset({JSONRPC_UNAUTHORIZED, JSONRPC_FORBIDDEN})

AuthzKind = Literal["unauthorized", "forbidden"]


@dataclass(frozen=True)
class AuthzFailure:
    """401 / 403 の中身(トークンは含まない)。"""

    kind: AuthzKind
    http_status: int
    www_authenticate: str

    @classmethod
    def from_jsonrpc_error(cls, error: Any) -> AuthzFailure | None:
        """JSON-RPC エラー(dict か ``mcp.types.ErrorData``)から復元する。対象外なら ``None``。"""
        code = error.get("code") if isinstance(error, dict) else getattr(error, "code", None)
        if code not in AUTHZ_ERROR_CODES:
            return None
        data = error.get("data") if isinstance(error, dict) else getattr(error, "data", None)
        data = data if isinstance(data, dict) else {}
        status = int(data.get("http_status") or (401 if code == JSONRPC_UNAUTHORIZED else 403))
        return cls(
            kind="unauthorized" if code == JSONRPC_UNAUTHORIZED else "forbidden",
            http_status=status,
            www_authenticate=str(data.get("www_authenticate") or ""),
        )


def find_authz_failure(exc: BaseException | None) -> AuthzFailure | None:
    """例外の連鎖(``__cause__`` / ``inner_exception``)から 401 / 403 由来のものを探す。"""
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        error = getattr(exc, "error", None)  # mcp.shared.exceptions.McpError.error
        if error is not None:
            failure = AuthzFailure.from_jsonrpc_error(error)
            if failure is not None:
                return failure
        exc = getattr(exc, "inner_exception", None) or exc.__cause__ or exc.__context__
    return None


def _jsonrpc_id(request: httpx.Request) -> tuple[bool, Any]:
    """(JSON-RPC リクエストか, id)。通知(id なし)とバッチは (False, None)。"""
    try:
        payload = json.loads(request.content or b"null")
    except (httpx.RequestNotRead, ValueError):
        return False, None
    if isinstance(payload, dict) and "method" in payload and "id" in payload:
        return True, payload["id"]
    return False, None


class AuthzMappingTransport(httpx.AsyncBaseTransport):
    """``inner`` の前に立ち、JSON-RPC の POST への 401 / 403 を JSON-RPC エラーに変える。"""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        self._inner = inner

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._inner.handle_async_request(request)
        if request.method != "POST" or response.status_code not in (401, 403):
            return response
        www_authenticate = response.headers.get("www-authenticate", "")
        await response.aread()
        await response.aclose()
        is_request, request_id = _jsonrpc_id(request)
        if not is_request:
            # 通知への 401/403: 応答を返さない約束なので 202 として握りつぶす(次のリクエストで判明する)
            return httpx.Response(202, request=request)
        code = JSONRPC_UNAUTHORIZED if response.status_code == 401 else JSONRPC_FORBIDDEN
        body = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": "unauthorized" if code == JSONRPC_UNAUTHORIZED else "forbidden",
                "data": {"http_status": response.status_code, "www_authenticate": www_authenticate},
            },
        }
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            content=json.dumps(body).encode(),
            request=request,
        )

    async def aclose(self) -> None:
        await self._inner.aclose()

"""hosted agent → 中間層バックエンドへの「認可の結果」の伝え方(Responses のメタデータ)。

公式手順は「認証の失敗は中間層へ返し、中間層がトークンを取り直すか利用者に再認証を促す」
と求める。エージェントの応答は Responses API の形なので、判定結果は応答の ``metadata``
(文字列 → 文字列、最大 16 キー・値 512 文字)に載せる。本文(output_text)は利用者向けの
定型文(``MSG_REAUTH`` など)で、機械判定には使わない。

``status`` は ``completed`` のまま返す(再認証が必要なのはエラーではなく正常な判定結果)。
想定外の例外だけ ``failed``(code=server_error)にする。

このモジュールは MAF / Agent Server SDK に依存しない(バックエンドからも import する)。
"""

from __future__ import annotations

import re
from typing import Literal

#: 判定結果。``ok`` 以外のときバックエンドは回答を返さず、利用者に対処を求める
META_STATUS = "delegated_access_status"
#: 判定の理由(``missing_tools_token`` / ``mcp_unauthorized`` / ``tool_unauthorized`` など)
META_REASON = "delegated_access_reason"
#: MCP サーバー(または APIM)が 401 で返した ``WWW-Authenticate``(トークンは含まない)
META_WWW_AUTHENTICATE = "delegated_access_www_authenticate"
#: この利用者に見えた MCP サーバー / 見えなかった MCP サーバー(カンマ区切り、名前は契約どおり)
META_VISIBLE_SERVERS = "delegated_access_visible_servers"
META_HIDDEN_SERVERS = "delegated_access_hidden_servers"

AccessStatus = Literal["ok", "reauth_required", "error"]

STATUS_OK: AccessStatus = "ok"
STATUS_REAUTH: AccessStatus = "reauth_required"
STATUS_ERROR: AccessStatus = "error"

REASON_MISSING_TOKEN = "missing_tools_token"
REASON_MCP_UNAUTHORIZED = "mcp_unauthorized"  # 事前の疎通確認(initialize)で 401
REASON_TOOL_UNAUTHORIZED = "tool_unauthorized"  # ツール呼び出しの時点で 401
REASON_INTERNAL_ERROR = "internal_error"

#: メタデータ値の上限(Agent Server SDK の制約)
MAX_METADATA_VALUE_LENGTH = 512


def clip(value: str) -> str:
    """メタデータの値の上限に収める。"""
    return (
        value
        if len(value) <= MAX_METADATA_VALUE_LENGTH
        else value[: MAX_METADATA_VALUE_LENGTH - 1] + "…"
    )


_WWW_AUTH_PARAM_RE = re.compile(r'(\w+)="([^"]*)"')


def parse_www_authenticate(value: str) -> dict[str, str]:
    """``Bearer error="...", claims="..."`` をパラメーター名(小文字)→ 値の dict にする。"""
    return {k.lower(): v for k, v in _WWW_AUTH_PARAM_RE.findall(value or "")}

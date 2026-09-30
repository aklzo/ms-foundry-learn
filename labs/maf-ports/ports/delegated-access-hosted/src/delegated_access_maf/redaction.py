"""トークンのマスク(中間層バックエンドと hosted agent で共用)。

公式手順(use-on-behalf-of-flow の「Protect tokens」)は、トークンをプロンプト・モデル入力・
リクエスト本文・応答メタデータ・会話履歴・チェックポイント・出力・例外・ログのどこにも
出すなと求める。このモジュールはその「出さない」を 3 か所で担保する部品:

- ``Redactor``: 既知のトークン文字列(このリクエストの委任トークン)と、JWT / ``Bearer ...``
  の形をした文字列を ``[REDACTED]`` に置き換える。エージェントのミドルウェアが
  モデル入出力・ツール引数・ツール結果に使う
- ``secrets_scope``: いまのリクエストのトークンを ContextVar に載せる(ログフィルター用)
- ``RedactingLogFilter`` / ``install_log_redaction``: ルートロガーのハンドラーに付け、
  メッセージ・引数・例外のトレースバックをマスクしてから出力する(App Insights への
  エクスポートも同じハンドラー経由なので同時に守られる)

既知のトークンは完全一致で、未知のトークンは形(JWT は ``eyJ`` で始まる 3 区切り)で消す。
形で消すのは、MCP サーバーやモデルがトークンを「言い換えずに」反射したときの保険。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from .contracts import SENSITIVE_HEADERS

REDACTED = "[REDACTED]"

#: JWT(ヘッダー.ペイロード.署名)。ヘッダーは必ず ``{"`` → base64url で ``eyJ`` になる
_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]*")
#: ``Bearer <何か>``(JWT でない不透明トークンも含む)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")
#: 短すぎる値は完全一致マスクの対象にしない(一般語を誤って消さないため)
_MIN_SECRET_LENGTH = 8

_current_secrets: ContextVar[tuple[str, ...]] = ContextVar("delegated_access_secrets", default=())


class Redactor:
    """既知の秘密値+トークンらしい形をマスクする。1 リクエストに 1 つ作る。"""

    def __init__(self, secrets: Iterable[str | None] = ()) -> None:
        unique = {s for s in secrets if s and len(s) >= _MIN_SECRET_LENGTH}
        # 長い順に置換する(ある秘密値が別の秘密値の部分文字列でも取りこぼさない)
        self._secrets = tuple(sorted(unique, key=len, reverse=True))

    @property
    def secrets(self) -> tuple[str, ...]:
        return self._secrets

    def redact(self, text: str) -> str:
        if not text:
            return text
        for secret in self._secrets:
            if secret in text:
                text = text.replace(secret, REDACTED)
        text = _JWT_RE.sub(REDACTED, text)
        return _BEARER_RE.sub(f"Bearer {REDACTED}", text)

    def contains_secret(self, text: str) -> bool:
        """マスク対象が含まれるか(テストと監査用)。"""
        return bool(text) and self.redact(text) != text

    def redact_value(self, value: Any) -> Any:
        """文字列・dict・list・tuple を再帰的にマスクする(ツール引数用)。"""
        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, Mapping):
            return {k: self.redact_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.redact_value(v) for v in value]
        if isinstance(value, tuple):
            return tuple(self.redact_value(v) for v in value)
        return value


def redact_text(text: str) -> str:
    """いまのリクエストの秘密値(``secrets_scope``)+形でマスクする。ログ・例外文字列用。"""
    return Redactor(_current_secrets.get()).redact(text)


@contextmanager
def secrets_scope(*secrets: str | None) -> Iterator[None]:
    """このブロック(と、ここから生まれたタスク)のログで ``secrets`` をマスクする。"""
    merged = tuple(s for s in (*_current_secrets.get(), *secrets) if s)
    token = _current_secrets.set(merged)
    try:
        yield
    finally:
        _current_secrets.reset(token)


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """ログ出力用にヘッダーを複製し、``SENSITIVE_HEADERS`` の値を伏せる。"""
    return {
        name: (REDACTED if name.lower() in SENSITIVE_HEADERS else value)
        for name, value in headers.items()
    }


class RedactingLogFilter(logging.Filter):
    """ログレコードのメッセージと例外文字列をマスクする(ハンドラーに付ける)。

    ロガーに付けたフィルターは子ロガーから伝播したレコードに効かないため、
    ``install_log_redaction`` はルートロガーの**ハンドラー**に付ける。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - 書式エラーのレコードでもログは止めない
            message = str(record.msg)
        record.msg = redact_text(message)
        record.args = None
        if record.exc_info:
            text = logging.Formatter().formatException(record.exc_info)
            record.exc_text = redact_text(text)
            # 構造化された例外(トレースバック内の値)をエクスポーターに渡さない
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = redact_text(record.exc_text)
        if record.stack_info:
            record.stack_info = redact_text(record.stack_info)
        return True


_FILTER = RedactingLogFilter()


def install_log_redaction(logger: logging.Logger | None = None) -> int:
    """``logger``(既定はルート)の全ハンドラーにマスク用フィルターを付ける。付けた数を返す。

    ハンドラーを後から足すライブラリ(OTel / Azure Monitor)があるため、
    ホストの初期化が終わってから呼ぶ(hosting/main.py)。何度呼んでも重複しない。
    """
    target = logger or logging.getLogger()
    added = 0
    for handler in target.handlers:
        if _FILTER not in handler.filters:
            handler.addFilter(_FILTER)
            added += 1
    return added

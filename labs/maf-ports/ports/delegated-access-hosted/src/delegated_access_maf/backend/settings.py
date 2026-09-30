"""中間層バックエンドの設定(環境変数)。

- 共通: ``ENTRA_TENANT_ID`` / ``TOOLS_API_CLIENT_ID`` / ``TOOLS_API_SCOPE``
  (``api://<tools-client-id>/Tools.Access``。未設定ならクライアント ID から組み立てる)
- バックエンド: ``BACKEND_API_CLIENT_ID``(利用者トークンの ``aud``)/
  ``BACKEND_CLIENT_SECRET``(OBO と Foundry 用トークンの取得。機密クライアント)/
  ``AGENT_RESPONSES_URL``(hosted agent の Responses URL 全体。ローカルコンテナなら
  ``http://localhost:8088/responses``)/ ``FOUNDRY_SCOPE``(既定 ``https://ai.azure.com/.default``)
- 待ち受け: ``BACKEND_PORT``(既定 8000。CLI の ``BACKEND_URL`` と合わせる)

``AGENT_RESPONSES_URL`` がループバックなら「ローカルモード」: Foundry を通らないので
Foundry 用のワークロードトークン(``Authorization``)を付けない。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

from ..contracts import BACKEND_API_SCOPE_NAME, TOOLS_API_SCOPE_NAME
from ..jwt_validation import AUTHORITY_HOST

DEFAULT_FOUNDRY_SCOPE = "https://ai.azure.com/.default"
DEFAULT_BACKEND_PORT = 8000
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class SettingsError(ValueError):
    """必須の環境変数がない・値が不正。"""


@dataclass(frozen=True)
class BackendSettings:
    tenant_id: str
    backend_api_client_id: str
    tools_api_scope: str
    agent_responses_url: str
    backend_client_secret: str = ""
    foundry_scope: str = DEFAULT_FOUNDRY_SCOPE
    authority_host: str = AUTHORITY_HOST
    port: int = DEFAULT_BACKEND_PORT

    @property
    def authority(self) -> str:
        return f"{self.authority_host}/{self.tenant_id}"

    @property
    def backend_api_scope(self) -> str:
        """利用者の CLI が取得するスコープ(このバックエンド宛て)。"""
        return f"api://{self.backend_api_client_id}/{BACKEND_API_SCOPE_NAME}"

    @property
    def local_agent(self) -> bool:
        """エージェントがローカルのコンテナか(Foundry のトークンを付けない)。"""
        return (urlsplit(self.agent_responses_url).hostname or "") in _LOOPBACK_HOSTS

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> BackendSettings:
        env = os.environ if env is None else env

        def get(name: str) -> str:
            return (env.get(name) or "").strip()

        def required(name: str) -> str:
            value = get(name)
            if not value:
                raise SettingsError(f"環境変数 {name} が未設定です")
            return value

        tools_scope = get("TOOLS_API_SCOPE")
        if not tools_scope:
            tools_client_id = get("TOOLS_API_CLIENT_ID")
            if not tools_client_id:
                raise SettingsError("TOOLS_API_SCOPE か TOOLS_API_CLIENT_ID のどちらかが必要です")
            tools_scope = f"api://{tools_client_id}/{TOOLS_API_SCOPE_NAME}"
        agent_url = required("AGENT_RESPONSES_URL")
        parts = urlsplit(agent_url)
        if parts.scheme != "https" and (parts.hostname or "") not in _LOOPBACK_HOSTS:
            raise SettingsError(
                "AGENT_RESPONSES_URL はループバック以外では https:// にしてください"
            )
        return cls(
            tenant_id=required("ENTRA_TENANT_ID"),
            backend_api_client_id=required("BACKEND_API_CLIENT_ID"),
            tools_api_scope=tools_scope,
            agent_responses_url=agent_url,
            backend_client_secret=get("BACKEND_CLIENT_SECRET"),
            foundry_scope=get("FOUNDRY_SCOPE") or DEFAULT_FOUNDRY_SCOPE,
            port=int(get("BACKEND_PORT") or DEFAULT_BACKEND_PORT),
        )

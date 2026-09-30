"""hosted agent コンテナの設定(環境変数)。

- ``TOOLS_BASE_URL``: MCP の入口。方式 A なら APIM ゲートウェイ、方式 B ならツールサーバーの
  ベース URL。MCP の URL は ``TOOLS_BASE_URL + McpServerSpec.path``(contracts.py)
- ``FOUNDRY_PROJECT_ENDPOINT``: モデル呼び出し(エージェント自身の ID)用
- ``FOUNDRY_MODEL_NAME``: モデルのデプロイ名。プラットフォームが注入する
  ``AZURE_AI_MODEL_DEPLOYMENT_NAME`` があればそちらを優先
- ``MCP_TIMEOUT_SECONDS``(任意、既定 30)

**トークンを送る先は設定で固定する**(モデルの出力で URL を決めさせない — 公式手順の
「承認済みの HTTPS 宛先に限定」)。``http://`` はループバック(ローカル検証)だけ許す。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

from ..contracts import McpServerSpec

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
DEFAULT_MCP_TIMEOUT_SECONDS = 30.0


class SettingsError(ValueError):
    """必須の環境変数がない・値が不正。"""


def validate_tools_base_url(url: str) -> str:
    """委任トークンを送ってよい宛先か確かめ、末尾の ``/`` を落として返す。"""
    parts = urlsplit(url.strip())
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise SettingsError(f"TOOLS_BASE_URL は http(s) の絶対 URL にしてください(指定値: {url!r})")
    if parts.scheme == "http" and parts.hostname not in _LOOPBACK_HOSTS:
        raise SettingsError(
            "TOOLS_BASE_URL に http:// を使えるのはループバック(ローカル検証)だけです。"
            "委任トークンを平文で送らないため https:// にしてください"
        )
    if parts.query or parts.fragment:
        raise SettingsError("TOOLS_BASE_URL にクエリやフラグメントは付けられません")
    return url.strip().rstrip("/")


@dataclass(frozen=True)
class AgentSettings:
    tools_base_url: str
    project_endpoint: str = ""
    model: str = ""
    mcp_timeout_seconds: float = DEFAULT_MCP_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        object.__setattr__(self, "tools_base_url", validate_tools_base_url(self.tools_base_url))

    def mcp_url(self, spec: McpServerSpec) -> str:
        return f"{self.tools_base_url}{spec.path}"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> AgentSettings:
        env = os.environ if env is None else env
        base = (env.get("TOOLS_BASE_URL") or "").strip()
        if not base:
            raise SettingsError("環境変数 TOOLS_BASE_URL が未設定です")
        timeout = (env.get("MCP_TIMEOUT_SECONDS") or "").strip()
        return cls(
            tools_base_url=base,
            project_endpoint=(env.get("FOUNDRY_PROJECT_ENDPOINT") or "").strip(),
            model=(
                (env.get("AZURE_AI_MODEL_DEPLOYMENT_NAME") or "").strip()
                or (env.get("FOUNDRY_MODEL_NAME") or "").strip()
            ),
            mcp_timeout_seconds=float(timeout) if timeout else DEFAULT_MCP_TIMEOUT_SECONDS,
        )

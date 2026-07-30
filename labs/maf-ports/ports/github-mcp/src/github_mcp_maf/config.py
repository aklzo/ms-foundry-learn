"""環境変数ベースの設定。共有基盤(labs/maf-ports/infra/shared.bicep)の
出力を lab ルートの ``.env`` から読む。

Foundry まわりは ports/travel-memory/src/travel_memory_maf/config.py と同一。
本ポート固有分:

- ``GITHUB_TOKEN``(必須)— GitHub リモート MCP サーバーの PAT。
  ``gh auth token`` でも取得できる(未設定時の ConfigError で案内)
- ``GITHUB_MCP_URL``(既定: GitHub 公式リモート MCP サーバー)
- ``GITHUB_TOOLSETS``(既定 ``repos,issues,pull_requests`` — 元アプリが Docker
  コンテナへ渡していた環境変数と同名・同値。リモートでは X-MCP-Toolsets
  ヘッダーに変換される。tools.py 参照)
- ``GITHUB_MCP_READONLY``(既定 true — X-MCP-Readonly ヘッダー。本ポートは
  読み取り分析のみなので、書き込み系ツールをサーバー側で外す)

テスト容易性のため ``from_env(environ=...)`` は環境の注入シームを持つ
(指定時は .env の読み込みも行わない)。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

#: lab ルート(labs/maf-ports)の .env — 共有基盤の値を全ポートで共有する
LAB_ENV_PATH = Path(__file__).resolve().parents[3].parent / ".env"

#: GitHub 公式リモート MCP サーバー(GA)。stdio 版 ghcr.io/github/github-mcp-server の置き換え
DEFAULT_GITHUB_MCP_URL = "https://api.githubcopilot.com/mcp/"

#: 元アプリの GITHUB_TOOLSETS と同値(repos / issues / pull_requests のみ公開)
DEFAULT_TOOLSETS = "repos,issues,pull_requests"

_FALSY = frozenset({"0", "false", "no", "off"})


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class GithubMcpSettings:
    """Foundry プロジェクト(チャットモデル)+ GitHub リモート MCP への接続情報。"""

    openai_v1_endpoint: str
    model: str
    api_key: str
    github_token: str
    mcp_url: str
    toolsets: str
    readonly: bool
    app_insights_connection_string: str | None

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> GithubMcpSettings:
        if environ is None:
            # カレント → lab ルートの順で .env を読む(既存の環境変数を優先)
            load_dotenv()
            if LAB_ENV_PATH.is_file():
                load_dotenv(LAB_ENV_PATH)
            environ = os.environ

        endpoint = environ.get("FOUNDRY_OPENAI_V1_ENDPOINT", "")
        model = environ.get("FOUNDRY_MODEL", "")
        api_key = environ.get("FOUNDRY_API_KEY", "")
        github_token = environ.get("GITHUB_TOKEN", "")
        missing = [
            name
            for name, value in (
                ("FOUNDRY_OPENAI_V1_ENDPOINT", endpoint),
                ("FOUNDRY_MODEL", model),
                ("FOUNDRY_API_KEY", api_key),
                ("GITHUB_TOKEN", github_token),
            )
            if not value
        ]
        if missing:
            hint = "labs/maf-ports/.env を確認"
            if "GITHUB_TOKEN" in missing:
                hint += (
                    "。GITHUB_TOKEN は `gh auth token` でも取得可: "
                    'export GITHUB_TOKEN="$(gh auth token)"'
                )
            raise ConfigError(f"環境変数が未設定: {', '.join(missing)}({hint})")
        return cls(
            openai_v1_endpoint=endpoint,
            model=model,
            api_key=api_key,
            github_token=github_token,
            mcp_url=environ.get("GITHUB_MCP_URL", DEFAULT_GITHUB_MCP_URL),
            toolsets=environ.get("GITHUB_TOOLSETS", DEFAULT_TOOLSETS),
            readonly=environ.get("GITHUB_MCP_READONLY", "true").strip().lower() not in _FALSY,
            app_insights_connection_string=environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
            or None,
        )

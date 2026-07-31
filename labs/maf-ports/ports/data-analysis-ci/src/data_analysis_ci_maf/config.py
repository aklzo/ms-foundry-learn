"""環境変数ベースの設定。共有基盤(labs/maf-ports/infra/shared.bicep)の
出力を lab ルートの ``.env`` から読む。

Foundry まわりは ports/github-mcp/src/github_mcp_maf/config.py と同一。
本ポート固有の環境変数はない — Code Interpreter は **OpenAI v1 Responses API
のサーバー側ツール**なので、接続情報は共有基盤の 3 点
(FOUNDRY_OPENAI_V1_ENDPOINT / FOUNDRY_MODEL / FOUNDRY_API_KEY)だけで足りる。

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


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class FoundrySettings:
    """Foundry プロジェクト(OpenAI v1 エンドポイント)への接続情報。"""

    openai_v1_endpoint: str
    model: str
    api_key: str
    app_insights_connection_string: str | None

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> FoundrySettings:
        if environ is None:
            # カレント → lab ルートの順で .env を読む(既存の環境変数を優先)
            load_dotenv()
            if LAB_ENV_PATH.is_file():
                load_dotenv(LAB_ENV_PATH)
            environ = os.environ

        endpoint = environ.get("FOUNDRY_OPENAI_V1_ENDPOINT", "")
        model = environ.get("FOUNDRY_MODEL", "")
        api_key = environ.get("FOUNDRY_API_KEY", "")
        missing = [
            name
            for name, value in (
                ("FOUNDRY_OPENAI_V1_ENDPOINT", endpoint),
                ("FOUNDRY_MODEL", model),
                ("FOUNDRY_API_KEY", api_key),
            )
            if not value
        ]
        if missing:
            raise ConfigError(
                f"環境変数が未設定: {', '.join(missing)}(labs/maf-ports/.env を確認)"
            )
        return cls(
            openai_v1_endpoint=endpoint,
            model=model,
            api_key=api_key,
            app_insights_connection_string=environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
            or None,
        )

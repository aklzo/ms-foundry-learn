"""環境変数ベースの設定。共有基盤(labs/maf-ports/infra/shared.bicep)の
出力を lab ルートの ``.env`` から読む。

Foundry まわりは ports/research-handoff/src/research_handoff_maf/config.py と
同一。本ポート固有分として Azure AI Search(infra/main.bicep の出力)と
埋め込みデプロイ名を追加している。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

#: lab ルート(labs/maf-ports)の .env — 共有基盤の値を全ポートで共有する
LAB_ENV_PATH = Path(__file__).resolve().parents[3].parent / ".env"

#: 既定のインデックス名(scripts/setup_index.py が作成する)
DEFAULT_INDEX_NAME = "corrective-rag"

#: 既定の埋め込みデプロイ名(infra/main.bicep が共有 Foundry アカウントに追加)
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class CorrectiveRagSettings:
    """Foundry プロジェクト+Azure AI Search への接続情報。"""

    openai_v1_endpoint: str
    model: str
    api_key: str
    embedding_model: str
    search_endpoint: str
    search_api_key: str
    search_index: str
    app_insights_connection_string: str | None

    @classmethod
    def from_env(cls) -> CorrectiveRagSettings:
        # カレント → lab ルートの順で .env を読む(既存の環境変数を優先)
        load_dotenv()
        if LAB_ENV_PATH.is_file():
            load_dotenv(LAB_ENV_PATH)

        endpoint = os.environ.get("FOUNDRY_OPENAI_V1_ENDPOINT", "")
        model = os.environ.get("FOUNDRY_MODEL", "")
        api_key = os.environ.get("FOUNDRY_API_KEY", "")
        search_endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT", "")
        search_api_key = os.environ.get("AZURE_SEARCH_ADMIN_KEY", "")
        missing = [
            name
            for name, value in (
                ("FOUNDRY_OPENAI_V1_ENDPOINT", endpoint),
                ("FOUNDRY_MODEL", model),
                ("FOUNDRY_API_KEY", api_key),
                ("AZURE_SEARCH_ENDPOINT", search_endpoint),
                ("AZURE_SEARCH_ADMIN_KEY", search_api_key),
            )
            if not value
        ]
        if missing:
            raise ConfigError(
                f"環境変数が未設定: {', '.join(missing)}(labs/maf-ports/.env を確認。"
                "AZURE_SEARCH_* は ports/corrective-rag/infra/main.bicep の出力)"
            )
        return cls(
            openai_v1_endpoint=endpoint,
            model=model,
            api_key=api_key,
            embedding_model=os.environ.get("FOUNDRY_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
            search_endpoint=search_endpoint,
            search_api_key=search_api_key,
            search_index=os.environ.get("AZURE_SEARCH_INDEX", DEFAULT_INDEX_NAME),
            app_insights_connection_string=os.environ.get(
                "APPLICATIONINSIGHTS_CONNECTION_STRING"
            )
            or None,
        )

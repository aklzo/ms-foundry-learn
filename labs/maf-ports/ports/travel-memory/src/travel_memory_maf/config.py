"""環境変数ベースの設定。共有基盤(labs/maf-ports/infra/shared.bicep)の
出力を lab ルートの ``.env`` から読む。

Foundry まわりは ports/corrective-rag/src/corrective_rag_maf/config.py と
同一。本ポート固有分:

- ``FOUNDRY_PROJECT_ENDPOINT`` を必須にする(Memory ストアはプロジェクトの
  データプレーン API。認証は API キーではなく Entra ID —
  ``DefaultAzureCredential`` を使うため ``az login`` が必要)
- ``MEMORY_STORE_NAME``(既定 ``travel_memory``。scripts/setup_memory.py が
  作成する)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

#: lab ルート(labs/maf-ports)の .env — 共有基盤の値を全ポートで共有する
LAB_ENV_PATH = Path(__file__).resolve().parents[3].parent / ".env"

#: 既定の Memory ストア名(scripts/setup_memory.py が作成する)
DEFAULT_MEMORY_STORE_NAME = "travel_memory"


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class TravelMemorySettings:
    """Foundry プロジェクト(チャットモデル+Memory ストア)への接続情報。"""

    project_endpoint: str
    openai_v1_endpoint: str
    model: str
    api_key: str
    memory_store: str
    app_insights_connection_string: str | None

    @classmethod
    def from_env(cls) -> TravelMemorySettings:
        # カレント → lab ルートの順で .env を読む(既存の環境変数を優先)
        load_dotenv()
        if LAB_ENV_PATH.is_file():
            load_dotenv(LAB_ENV_PATH)

        project_endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "")
        endpoint = os.environ.get("FOUNDRY_OPENAI_V1_ENDPOINT", "")
        model = os.environ.get("FOUNDRY_MODEL", "")
        api_key = os.environ.get("FOUNDRY_API_KEY", "")
        missing = [
            name
            for name, value in (
                ("FOUNDRY_PROJECT_ENDPOINT", project_endpoint),
                ("FOUNDRY_OPENAI_V1_ENDPOINT", endpoint),
                ("FOUNDRY_MODEL", model),
                ("FOUNDRY_API_KEY", api_key),
            )
            if not value
        ]
        if missing:
            raise ConfigError(
                f"環境変数が未設定: {', '.join(missing)}(labs/maf-ports/.env を確認。"
                "Memory ストアの操作にはさらに az login 済みの Entra ID が必要)"
            )
        return cls(
            project_endpoint=project_endpoint,
            openai_v1_endpoint=endpoint,
            model=model,
            api_key=api_key,
            memory_store=os.environ.get("MEMORY_STORE_NAME", DEFAULT_MEMORY_STORE_NAME),
            app_insights_connection_string=os.environ.get(
                "APPLICATIONINSIGHTS_CONNECTION_STRING"
            )
            or None,
        )

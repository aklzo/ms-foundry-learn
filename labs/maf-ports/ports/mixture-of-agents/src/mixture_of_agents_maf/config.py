"""環境変数ベースの設定。共有基盤(labs/maf-ports/infra/shared.bicep)の
出力を lab ルートの ``.env`` から読む。

Port 2 固有:
- ``FOUNDRY_PROPOSER_MODELS``(カンマ区切り・省略可): proposer に使うモデル
  デプロイ名の一覧。未設定なら「``FOUNDRY_MODEL`` ×ペルソナ4体」モード。
- ``FOUNDRY_AGGREGATOR_MODEL``(省略可): アグリゲータのモデル。既定は
  ``FOUNDRY_MODEL``。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

#: lab ルート(labs/maf-ports)の .env — 共有基盤の値を全ポートで共有する
LAB_ENV_PATH = Path(__file__).resolve().parents[3].parent / ".env"


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class FoundrySettings:
    """Foundry プロジェクトへの接続情報。"""

    openai_v1_endpoint: str
    model: str
    api_key: str
    app_insights_connection_string: str | None
    #: proposer に使うモデルデプロイ名。空なら「model ×ペルソナ4体」モード
    proposer_models: tuple[str, ...] = ()
    #: アグリゲータのモデル。空は許さず from_env で model に落とす
    aggregator_model: str = ""

    @classmethod
    def from_env(cls) -> FoundrySettings:
        # カレント → lab ルートの順で .env を読む(既存の環境変数を優先)
        load_dotenv()
        if LAB_ENV_PATH.is_file():
            load_dotenv(LAB_ENV_PATH)

        endpoint = os.environ.get("FOUNDRY_OPENAI_V1_ENDPOINT", "")
        model = os.environ.get("FOUNDRY_MODEL", "")
        api_key = os.environ.get("FOUNDRY_API_KEY", "")
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
                f"環境変数が未設定: {', '.join(missing)}(labs/maf-ports/.env を確認。"
                "雛形は .env.example)"
            )
        proposer_models = tuple(
            m.strip()
            for m in os.environ.get("FOUNDRY_PROPOSER_MODELS", "").split(",")
            if m.strip()
        )
        return cls(
            openai_v1_endpoint=endpoint,
            model=model,
            api_key=api_key,
            app_insights_connection_string=os.environ.get(
                "APPLICATIONINSIGHTS_CONNECTION_STRING"
            )
            or None,
            proposer_models=proposer_models,
            aggregator_model=os.environ.get("FOUNDRY_AGGREGATOR_MODEL", "").strip() or model,
        )

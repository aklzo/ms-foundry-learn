"""環境変数ベースの設定。共有基盤(labs/maf-ports/infra/shared.bicep)の
出力を lab ルートの ``.env`` から読む。

Foundry の接続 3 点(FOUNDRY_OPENAI_V1_ENDPOINT / FOUNDRY_MODEL /
FOUNDRY_API_KEY)は他ポートと同一。本ポート固有分(すべて Voice Live 層のみが
使う。FNOL コアとテキスト対話層は 3 点だけで動く):

- ``VOICE_LIVE_ENDPOINT``(省略可): Voice Live の接続先。省略時は
  ``FOUNDRY_PROJECT_ENDPOINT`` のホストから導出する
  (https://<resource>.services.ai.azure.com/)。
- ``VOICE_LIVE_MODEL``(既定 ``gpt-4.1-mini``): Voice Live のマネージド提供
  モデル。**共有基盤の FOUNDRY_MODEL(gpt-5.4-mini)とは別** — 実装前調査
  (2026-07)で gpt-5.4-mini は Voice Live では BYOM 扱い(pre-deploy なし)、
  かつ Japan East では gpt-realtime 系が提供されないことを確認したため、
  Japan East で Global standard 提供の gpt-4.1-mini(Voice Live basic 価格帯)
  を既定にした。
- ``VOICE_LIVE_API_VERSION``(既定 ``2026-04-10``): 安定版 API。
- ``VOICE_LIVE_VOICE``(既定 ``en-US-AvaNeural``): azure-standard 音声。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

#: lab ルート(labs/maf-ports)の .env — 共有基盤の値を全ポートで共有する
LAB_ENV_PATH = Path(__file__).resolve().parents[3].parent / ".env"

DEFAULT_VOICE_LIVE_MODEL = "gpt-4.1-mini"
DEFAULT_VOICE_LIVE_API_VERSION = "2026-04-10"
DEFAULT_VOICE_LIVE_VOICE = "en-US-AvaNeural"


class ConfigError(RuntimeError):
    pass


def derive_voice_live_endpoint(project_endpoint: str) -> str:
    """プロジェクトエンドポイントから Voice Live 接続先(リソースルート)を導く。

    https://<res>.services.ai.azure.com/api/projects/<name>
      → https://<res>.services.ai.azure.com/
    """
    text = (project_endpoint or "").strip()
    if not text:
        return ""
    scheme, sep, rest = text.partition("://")
    if not sep:
        return ""
    host = rest.split("/", 1)[0]
    if not host:
        return ""
    return f"{scheme}://{host}/"


@dataclass(frozen=True)
class FoundrySettings:
    """Foundry プロジェクト+Voice Live への接続情報。"""

    openai_v1_endpoint: str
    model: str
    api_key: str
    app_insights_connection_string: str | None
    project_endpoint: str = ""
    voice_live_endpoint: str = ""
    voice_live_model: str = DEFAULT_VOICE_LIVE_MODEL
    voice_live_api_version: str = DEFAULT_VOICE_LIVE_API_VERSION
    voice_live_voice: str = DEFAULT_VOICE_LIVE_VOICE

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
        project_endpoint = environ.get("FOUNDRY_PROJECT_ENDPOINT", "").strip()
        voice_endpoint = environ.get("VOICE_LIVE_ENDPOINT", "").strip() or derive_voice_live_endpoint(
            project_endpoint
        )
        return cls(
            openai_v1_endpoint=endpoint,
            model=model,
            api_key=api_key,
            app_insights_connection_string=environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
            or None,
            project_endpoint=project_endpoint,
            voice_live_endpoint=voice_endpoint,
            voice_live_model=environ.get("VOICE_LIVE_MODEL", DEFAULT_VOICE_LIVE_MODEL),
            voice_live_api_version=environ.get(
                "VOICE_LIVE_API_VERSION", DEFAULT_VOICE_LIVE_API_VERSION
            ),
            voice_live_voice=environ.get("VOICE_LIVE_VOICE", DEFAULT_VOICE_LIVE_VOICE),
        )

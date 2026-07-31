"""環境変数ベースの設定。共有基盤(labs/maf-ports/infra/shared.bicep)の
出力を lab ルートの ``.env`` から読む。

Foundry の接続 3 点(FOUNDRY_OPENAI_V1_ENDPOINT / FOUNDRY_MODEL /
FOUNDRY_API_KEY)は ports/critique-loop/src/critique_loop_maf/config.py と
同一。本ポート固有分:

- ``AZURE_SEARCH_ENDPOINT`` / ``AZURE_SEARCH_ADMIN_KEY``(必須)—
  ports/db-routing-iq/infra/main.bicep の出力。knowledge base の管理
  (scripts/setup_kb.py)と MCP エンドポイントの認証(api-key ヘッダー)の
  両方に使う
- ``DB_ROUTING_KB_NAME``(既定 ``db-routing-kb``)— knowledge base 名。
  MCP エンドポイント URL は :attr:`DbRoutingIqSettings.kb_mcp_url` が導出する

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

#: 既定の knowledge base 名(scripts/setup_kb.py が作成する)
DEFAULT_KB_NAME = "db-routing-kb"

#: agentic retrieval(knowledge source / knowledge base / MCP)の API バージョン。
#: 2026-04-01(GA)は最小限の抽出検索のみ。**LLM クエリプランニング
#: (= 本ポートの核心であるサービス側ルーティング)を非 Web ソースで使うには
#: 2026-05-01-preview が必要**(実装前調査の結論。README 参照)。
SEARCH_API_VERSION = "2026-05-01-preview"


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class DbRoutingIqSettings:
    """Foundry プロジェクト+Azure AI Search(knowledge base)への接続情報。"""

    openai_v1_endpoint: str
    model: str
    api_key: str
    search_endpoint: str
    search_api_key: str
    kb_name: str
    app_insights_connection_string: str | None

    @property
    def foundry_openai_resource_uri(self) -> str:
        """knowledge base の models[].azureOpenAIParameters.resourceUri 用。

        共有基盤の出力は OpenAI v1 互換エンドポイント
        (``https://<sub>.openai.azure.com/openai/v1``)なので、KB 定義が
        要求するリソース URI(``https://<sub>.openai.azure.com``)に落とす。
        """
        return self.openai_v1_endpoint.removesuffix("/").removesuffix("/openai/v1")

    @property
    def kb_mcp_url(self) -> str:
        """knowledge base ごとに公開される MCP エンドポイント。

        形式: ``{search-endpoint}/knowledgebases/{kb}/mcp?api-version=...``
        (公開ツールは knowledge_base_retrieve のみ)。
        """
        base = self.search_endpoint.removesuffix("/")
        return f"{base}/knowledgebases/{self.kb_name}/mcp?api-version={SEARCH_API_VERSION}"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> DbRoutingIqSettings:
        if environ is None:
            # カレント → lab ルートの順で .env を読む(既存の環境変数を優先)
            load_dotenv()
            if LAB_ENV_PATH.is_file():
                load_dotenv(LAB_ENV_PATH)
            environ = os.environ

        endpoint = environ.get("FOUNDRY_OPENAI_V1_ENDPOINT", "")
        model = environ.get("FOUNDRY_MODEL", "")
        api_key = environ.get("FOUNDRY_API_KEY", "")
        search_endpoint = environ.get("AZURE_SEARCH_ENDPOINT", "")
        search_api_key = environ.get("AZURE_SEARCH_ADMIN_KEY", "")
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
                "AZURE_SEARCH_* は ports/db-routing-iq/infra/main.bicep の出力)"
            )
        return cls(
            openai_v1_endpoint=endpoint,
            model=model,
            api_key=api_key,
            search_endpoint=search_endpoint,
            search_api_key=search_api_key,
            kb_name=environ.get("DB_ROUTING_KB_NAME", DEFAULT_KB_NAME),
            app_insights_connection_string=environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
            or None,
        )

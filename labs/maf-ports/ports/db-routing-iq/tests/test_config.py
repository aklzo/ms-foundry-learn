"""設定(環境変数)と導出 URL のオフラインテスト。"""

import pytest

from db_routing_iq_maf.config import (
    DEFAULT_KB_NAME,
    SEARCH_API_VERSION,
    ConfigError,
    DbRoutingIqSettings,
)

ENV = {
    "FOUNDRY_OPENAI_V1_ENDPOINT": "https://aif-example.openai.azure.com/openai/v1",
    "FOUNDRY_MODEL": "gpt-5.4-mini",
    "FOUNDRY_API_KEY": "foundry-key",
    "AZURE_SEARCH_ENDPOINT": "https://srch-example.search.windows.net",
    "AZURE_SEARCH_ADMIN_KEY": "search-key",
}


def test_from_env_reads_all_values() -> None:
    settings = DbRoutingIqSettings.from_env(ENV)

    assert settings.model == "gpt-5.4-mini"
    assert settings.search_endpoint == "https://srch-example.search.windows.net"
    assert settings.kb_name == DEFAULT_KB_NAME == "db-routing-kb"
    assert settings.app_insights_connection_string is None


def test_missing_variables_are_listed_in_error() -> None:
    with pytest.raises(ConfigError) as exc_info:
        DbRoutingIqSettings.from_env({"FOUNDRY_MODEL": "gpt-5.4-mini"})

    message = str(exc_info.value)
    assert "FOUNDRY_OPENAI_V1_ENDPOINT" in message
    assert "AZURE_SEARCH_ENDPOINT" in message
    assert "AZURE_SEARCH_ADMIN_KEY" in message
    assert "FOUNDRY_MODEL" not in message.split("(")[0]


def test_kb_name_override() -> None:
    settings = DbRoutingIqSettings.from_env({**ENV, "DB_ROUTING_KB_NAME": "other-kb"})

    assert settings.kb_name == "other-kb"
    assert "/knowledgebases/other-kb/mcp" in settings.kb_mcp_url


def test_kb_mcp_url_shape() -> None:
    """MCP エンドポイントの公式形式:
    {search-endpoint}/knowledgebases/{kb}/mcp?api-version=..."""
    settings = DbRoutingIqSettings.from_env(ENV)

    assert settings.kb_mcp_url == (
        "https://srch-example.search.windows.net/knowledgebases/db-routing-kb/mcp"
        f"?api-version={SEARCH_API_VERSION}"
    )


def test_kb_mcp_url_tolerates_trailing_slash_on_endpoint() -> None:
    settings = DbRoutingIqSettings.from_env(
        {**ENV, "AZURE_SEARCH_ENDPOINT": "https://srch-example.search.windows.net/"}
    )

    assert "net//" not in settings.kb_mcp_url


def test_foundry_openai_resource_uri_strips_v1_path() -> None:
    """KB の models[].azureOpenAIParameters.resourceUri はリソース URI
    (パスなし)を要求する。"""
    settings = DbRoutingIqSettings.from_env(ENV)

    assert settings.foundry_openai_resource_uri == "https://aif-example.openai.azure.com"


def test_foundry_openai_resource_uri_tolerates_trailing_slash() -> None:
    settings = DbRoutingIqSettings.from_env(
        {**ENV, "FOUNDRY_OPENAI_V1_ENDPOINT": "https://aif-example.openai.azure.com/openai/v1/"}
    )

    assert settings.foundry_openai_resource_uri == "https://aif-example.openai.azure.com"


def test_api_version_is_the_preview_that_supports_llm_routing() -> None:
    """2026-04-01(GA)は最小抽出検索のみ。LLM クエリプランニング
    (サービス側ルーティング=本ポートの核心)には preview が必要。"""
    assert SEARCH_API_VERSION == "2026-05-01-preview"

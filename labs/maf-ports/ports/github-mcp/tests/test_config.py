"""設定のオフラインテスト。``from_env(environ=...)`` の注入シームを使い、
.env / プロセス環境に依存せず検証する(environ 指定時は load_dotenv しない)。"""

import pytest

from github_mcp_maf.config import (
    DEFAULT_GITHUB_MCP_URL,
    DEFAULT_TOOLSETS,
    ConfigError,
    GithubMcpSettings,
)

BASE_ENV = {
    "FOUNDRY_OPENAI_V1_ENDPOINT": "https://example.openai.azure.com/openai/v1",
    "FOUNDRY_MODEL": "gpt-5.4-mini",
    "FOUNDRY_API_KEY": "dummy",
    "GITHUB_TOKEN": "ghp_dummy",
}


def test_defaults_point_to_official_remote_server() -> None:
    settings = GithubMcpSettings.from_env(environ=BASE_ENV)

    assert settings.mcp_url == DEFAULT_GITHUB_MCP_URL == "https://api.githubcopilot.com/mcp/"
    assert settings.toolsets == DEFAULT_TOOLSETS == "repos,issues,pull_requests"
    assert settings.readonly is True
    assert settings.github_token == "ghp_dummy"
    assert settings.app_insights_connection_string is None


def test_missing_github_token_mentions_gh_auth_token() -> None:
    env = {name: value for name, value in BASE_ENV.items() if name != "GITHUB_TOKEN"}

    with pytest.raises(ConfigError) as excinfo:
        GithubMcpSettings.from_env(environ=env)

    message = str(excinfo.value)
    assert "GITHUB_TOKEN" in message
    assert "gh auth token" in message


def test_missing_foundry_settings_are_listed() -> None:
    with pytest.raises(ConfigError) as excinfo:
        GithubMcpSettings.from_env(environ={"GITHUB_TOKEN": "ghp_dummy"})

    message = str(excinfo.value)
    for name in ("FOUNDRY_OPENAI_V1_ENDPOINT", "FOUNDRY_MODEL", "FOUNDRY_API_KEY"):
        assert name in message
    # トークンはあるので gh auth token の案内は出ない
    assert "gh auth token" not in message


def test_env_overrides_for_url_toolsets_and_readonly() -> None:
    env = BASE_ENV | {
        "GITHUB_MCP_URL": "https://mcp.example.test/mcp/",
        "GITHUB_TOOLSETS": "repos",
        "GITHUB_MCP_READONLY": "false",
    }

    settings = GithubMcpSettings.from_env(environ=env)

    assert settings.mcp_url == "https://mcp.example.test/mcp/"
    assert settings.toolsets == "repos"
    assert settings.readonly is False

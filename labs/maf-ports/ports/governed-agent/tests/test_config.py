"""設定(環境変数)まわりのテスト。"""

from __future__ import annotations

import pytest

from governed_agent_maf.config import ConfigError, FoundrySettings

FULL_ENV = {
    "FOUNDRY_OPENAI_V1_ENDPOINT": "https://res.openai.azure.com/openai/v1",
    "FOUNDRY_MODEL": "gpt-5.4-mini",
    "FOUNDRY_API_KEY": "key-123",
    "FOUNDRY_PROJECT_ENDPOINT": "https://res.services.ai.azure.com/api/projects/maf-ports",
    "APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=abc",
}


def test_from_env_parses_all_fields() -> None:
    settings = FoundrySettings.from_env(FULL_ENV)
    assert settings.openai_v1_endpoint == FULL_ENV["FOUNDRY_OPENAI_V1_ENDPOINT"]
    assert settings.model == "gpt-5.4-mini"
    assert settings.api_key == "key-123"
    assert settings.project_endpoint.endswith("/maf-ports")
    assert settings.app_insights_connection_string == "InstrumentationKey=abc"


def test_missing_required_vars_raise_with_names() -> None:
    with pytest.raises(ConfigError) as exc:
        FoundrySettings.from_env({"FOUNDRY_MODEL": "m"})
    message = str(exc.value)
    assert "FOUNDRY_OPENAI_V1_ENDPOINT" in message
    assert "FOUNDRY_API_KEY" in message
    assert "FOUNDRY_MODEL" not in message


def test_optional_fields_default_to_empty() -> None:
    required_only = {k: FULL_ENV[k] for k in ("FOUNDRY_OPENAI_V1_ENDPOINT", "FOUNDRY_MODEL", "FOUNDRY_API_KEY")}
    settings = FoundrySettings.from_env(required_only)
    assert settings.project_endpoint == ""
    assert settings.app_insights_connection_string is None

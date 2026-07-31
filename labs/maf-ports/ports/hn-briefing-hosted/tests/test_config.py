"""設定(from_env)のオフラインテスト。"""

import pytest

from hn_briefing_maf.config import DEFAULT_AGENT_NAME, ConfigError, FoundrySettings

FULL_ENV = {
    "FOUNDRY_OPENAI_V1_ENDPOINT": "https://sub.openai.azure.com/openai/v1",
    "FOUNDRY_MODEL": "gpt-fake",
    "FOUNDRY_API_KEY": "key",
}


def test_from_env_reads_required_and_defaults() -> None:
    settings = FoundrySettings.from_env(FULL_ENV)

    assert settings.model == "gpt-fake"
    assert settings.app_insights_connection_string is None
    assert settings.project_endpoint == ""  # CLI には不要(スクリプトのみ必須)
    assert settings.agent_name == DEFAULT_AGENT_NAME


def test_from_env_reads_optional_port_specific_values() -> None:
    settings = FoundrySettings.from_env(
        {
            **FULL_ENV,
            "FOUNDRY_PROJECT_ENDPOINT": "https://sub.services.ai.azure.com/api/projects/p ",
            "HN_BRIEFING_AGENT_NAME": "my-briefing",
            "APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=x",
        }
    )

    assert settings.project_endpoint.endswith("/projects/p")  # strip される
    assert settings.agent_name == "my-briefing"
    assert settings.app_insights_connection_string == "InstrumentationKey=x"


def test_from_env_lists_all_missing_variables() -> None:
    with pytest.raises(ConfigError) as excinfo:
        FoundrySettings.from_env({"FOUNDRY_MODEL": "gpt-fake"})

    message = str(excinfo.value)
    assert "FOUNDRY_OPENAI_V1_ENDPOINT" in message
    assert "FOUNDRY_API_KEY" in message
    assert "FOUNDRY_MODEL" not in message

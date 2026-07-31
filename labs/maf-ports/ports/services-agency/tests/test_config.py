"""設定(config.py)のオフラインテスト。"""

import pytest

from services_agency_maf.config import ConfigError, FoundrySettings

COMPLETE = {
    "FOUNDRY_OPENAI_V1_ENDPOINT": "https://example.openai.azure.com/openai/v1",
    "FOUNDRY_MODEL": "gpt-5.4-mini",
    "FOUNDRY_API_KEY": "secret",
}


def test_from_env_reads_required_values() -> None:
    settings = FoundrySettings.from_env(COMPLETE)
    assert settings.openai_v1_endpoint == COMPLETE["FOUNDRY_OPENAI_V1_ENDPOINT"]
    assert settings.model == "gpt-5.4-mini"
    assert settings.api_key == "secret"
    assert settings.app_insights_connection_string is None


def test_from_env_reads_optional_app_insights() -> None:
    settings = FoundrySettings.from_env(
        {**COMPLETE, "APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=x"}
    )
    assert settings.app_insights_connection_string == "InstrumentationKey=x"


def test_from_env_lists_all_missing_names() -> None:
    with pytest.raises(ConfigError) as excinfo:
        FoundrySettings.from_env({"FOUNDRY_MODEL": "m"})
    message = str(excinfo.value)
    assert "FOUNDRY_OPENAI_V1_ENDPOINT" in message
    assert "FOUNDRY_API_KEY" in message
    assert "FOUNDRY_MODEL" not in message

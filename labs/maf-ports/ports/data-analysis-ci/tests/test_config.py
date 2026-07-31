"""設定のオフラインテスト。``from_env(environ=...)`` の注入シームを使い、
.env / プロセス環境に依存せず検証する(environ 指定時は load_dotenv しない)。"""

import pytest

from data_analysis_ci_maf.config import ConfigError, FoundrySettings

BASE_ENV = {
    "FOUNDRY_OPENAI_V1_ENDPOINT": "https://example.openai.azure.com/openai/v1",
    "FOUNDRY_MODEL": "gpt-5.4-mini",
    "FOUNDRY_API_KEY": "dummy",
}


def test_settings_from_env() -> None:
    settings = FoundrySettings.from_env(environ=BASE_ENV)

    assert settings.openai_v1_endpoint == BASE_ENV["FOUNDRY_OPENAI_V1_ENDPOINT"]
    assert settings.model == "gpt-5.4-mini"
    assert settings.api_key == "dummy"
    assert settings.app_insights_connection_string is None


def test_missing_settings_are_listed() -> None:
    with pytest.raises(ConfigError) as excinfo:
        FoundrySettings.from_env(environ={"FOUNDRY_MODEL": "gpt-5.4-mini"})

    message = str(excinfo.value)
    for name in ("FOUNDRY_OPENAI_V1_ENDPOINT", "FOUNDRY_API_KEY"):
        assert name in message
    assert "FOUNDRY_MODEL" not in message


def test_app_insights_connection_string_is_optional() -> None:
    env = BASE_ENV | {"APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=abc"}

    settings = FoundrySettings.from_env(environ=env)

    assert settings.app_insights_connection_string == "InstrumentationKey=abc"

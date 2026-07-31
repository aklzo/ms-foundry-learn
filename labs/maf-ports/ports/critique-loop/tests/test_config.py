"""設定(config.py)のオフラインテスト。environ 注入シームで .env に依存しない。"""

import pytest

from critique_loop_maf.config import ConfigError, FoundrySettings

BASE_ENV = {
    "FOUNDRY_OPENAI_V1_ENDPOINT": "https://example.openai.azure.com/openai/v1",
    "FOUNDRY_MODEL": "gpt-5.4-mini",
    "FOUNDRY_API_KEY": "dummy",
}


def test_from_env_reads_required_settings() -> None:
    settings = FoundrySettings.from_env(environ=BASE_ENV)

    assert settings.openai_v1_endpoint == BASE_ENV["FOUNDRY_OPENAI_V1_ENDPOINT"]
    assert settings.model == "gpt-5.4-mini"
    assert settings.api_key == "dummy"
    assert settings.app_insights_connection_string is None
    assert settings.project_endpoint == ""


def test_missing_required_vars_listed_in_error() -> None:
    with pytest.raises(ConfigError) as exc:
        FoundrySettings.from_env(environ={"FOUNDRY_MODEL": "gpt-5.4-mini"})
    message = str(exc.value)
    assert "FOUNDRY_OPENAI_V1_ENDPOINT" in message
    assert "FOUNDRY_API_KEY" in message
    assert "FOUNDRY_MODEL" not in message


def test_project_endpoint_is_optional_extra() -> None:
    """FOUNDRY_PROJECT_ENDPOINT はループ実行に不要(クラウド評価スクリプト
    だけが使う)ため、必須 3 点に含めない。"""
    settings = FoundrySettings.from_env(
        environ={
            **BASE_ENV,
            "FOUNDRY_PROJECT_ENDPOINT": " https://example.services.ai.azure.com/api/projects/p ",
            "APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=x",
        }
    )
    assert settings.project_endpoint.startswith("https://")  # strip 済み
    assert settings.app_insights_connection_string == "InstrumentationKey=x"


def test_empty_app_insights_normalized_to_none() -> None:
    settings = FoundrySettings.from_env(
        environ={**BASE_ENV, "APPLICATIONINSIGHTS_CONNECTION_STRING": ""}
    )
    assert settings.app_insights_connection_string is None

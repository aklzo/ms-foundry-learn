"""設定(config.py)のオフラインテスト。環境注入シームを使いネットワーク不要。"""

from __future__ import annotations

import pytest

from claim_voice_live_maf.config import (
    DEFAULT_VOICE_LIVE_API_VERSION,
    DEFAULT_VOICE_LIVE_MODEL,
    ConfigError,
    FoundrySettings,
)

BASE_ENV = {
    "FOUNDRY_OPENAI_V1_ENDPOINT": "https://aif-x.openai.azure.com/openai/v1",
    "FOUNDRY_MODEL": "gpt-5.4-mini",
    "FOUNDRY_API_KEY": "k",
}


def test_missing_required_env_raises_with_names() -> None:
    with pytest.raises(ConfigError) as exc:
        FoundrySettings.from_env(environ={"FOUNDRY_MODEL": "m"})
    assert "FOUNDRY_OPENAI_V1_ENDPOINT" in str(exc.value)
    assert "FOUNDRY_API_KEY" in str(exc.value)


def test_defaults_for_voice_live_settings() -> None:
    settings = FoundrySettings.from_env(environ=BASE_ENV)
    assert settings.voice_live_model == DEFAULT_VOICE_LIVE_MODEL == "gpt-4.1-mini"
    assert settings.voice_live_api_version == DEFAULT_VOICE_LIVE_API_VERSION == "2026-04-10"
    assert settings.voice_live_voice == "en-US-AvaNeural"
    assert settings.voice_live_endpoint == ""  # project endpoint なしでは導出できない


def test_voice_live_endpoint_derived_from_project_endpoint() -> None:
    env = BASE_ENV | {
        "FOUNDRY_PROJECT_ENDPOINT": "https://aif-x.services.ai.azure.com/api/projects/maf-ports"
    }
    settings = FoundrySettings.from_env(environ=env)
    assert settings.voice_live_endpoint == "https://aif-x.services.ai.azure.com/"


def test_voice_live_env_overrides_win() -> None:
    env = BASE_ENV | {
        "FOUNDRY_PROJECT_ENDPOINT": "https://aif-x.services.ai.azure.com/api/projects/maf-ports",
        "VOICE_LIVE_ENDPOINT": "https://override.services.ai.azure.com/",
        "VOICE_LIVE_MODEL": "gpt-5-mini",
        "VOICE_LIVE_API_VERSION": "2025-10-01",
        "VOICE_LIVE_VOICE": "ja-JP-NanamiNeural",
    }
    settings = FoundrySettings.from_env(environ=env)
    assert settings.voice_live_endpoint == "https://override.services.ai.azure.com/"
    assert settings.voice_live_model == "gpt-5-mini"
    assert settings.voice_live_api_version == "2025-10-01"
    assert settings.voice_live_voice == "ja-JP-NanamiNeural"

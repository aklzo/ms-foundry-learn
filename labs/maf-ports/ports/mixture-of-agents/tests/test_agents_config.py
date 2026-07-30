"""proposer 構成ロジックと設定パースのオフラインテスト(ネットワーク不要)。"""

import pytest

from mixture_of_agents_maf.agents import (
    NEUTRAL_PROPOSER_INSTRUCTIONS,
    PERSONAS,
    build_proposer_specs,
)
from mixture_of_agents_maf.config import FoundrySettings


def make_settings(**overrides) -> FoundrySettings:
    defaults = {
        "openai_v1_endpoint": "https://example.openai.azure.com/openai/v1",
        "model": "gpt-5.4-mini",
        "api_key": "dummy",
        "app_insights_connection_string": None,
        "aggregator_model": "gpt-5.4-mini",
    }
    defaults.update(overrides)
    return FoundrySettings(**defaults)


def test_default_is_four_personas_on_single_model() -> None:
    specs = build_proposer_specs(make_settings())

    assert [s.name for s in specs] == [name for name, _ in PERSONAS]
    assert all(s.model == "gpt-5.4-mini" for s in specs)
    # 多様性の源泉はペルソナ差: instructions は全て異なる
    assert len({s.instructions for s in specs}) == len(specs)


def test_multi_model_mode_one_proposer_per_model() -> None:
    specs = build_proposer_specs(
        make_settings(proposer_models=("gpt-5.4-mini", "phi-4", "gpt-5.4-mini"))
    )

    assert [s.model for s in specs] == ["gpt-5.4-mini", "phi-4", "gpt-5.4-mini"]
    # 同一モデルが重複しても executor id 衝突しないよう名前は一意
    assert len({s.name for s in specs}) == 3
    # 多様性はモデル差から得るため instructions は中立で共通
    assert all(s.instructions == NEUTRAL_PROPOSER_INSTRUCTIONS for s in specs)


def test_single_entry_proposer_models_uses_personas() -> None:
    specs = build_proposer_specs(make_settings(proposer_models=("phi-4",)))

    assert [s.name for s in specs] == [name for name, _ in PERSONAS]
    assert all(s.model == "phi-4" for s in specs)


def test_from_env_parses_proposer_and_aggregator_models(monkeypatch) -> None:
    monkeypatch.setenv("FOUNDRY_OPENAI_V1_ENDPOINT", "https://example/openai/v1")
    monkeypatch.setenv("FOUNDRY_MODEL", "gpt-5.4-mini")
    monkeypatch.setenv("FOUNDRY_API_KEY", "dummy")
    monkeypatch.setenv("FOUNDRY_PROPOSER_MODELS", " phi-4 , mistral-large ,, ")
    monkeypatch.setenv("FOUNDRY_AGGREGATOR_MODEL", "gpt-5.4")

    settings = FoundrySettings.from_env()
    assert settings.proposer_models == ("phi-4", "mistral-large")
    assert settings.aggregator_model == "gpt-5.4"


def test_from_env_defaults_when_optional_vars_empty(monkeypatch) -> None:
    monkeypatch.setenv("FOUNDRY_OPENAI_V1_ENDPOINT", "https://example/openai/v1")
    monkeypatch.setenv("FOUNDRY_MODEL", "gpt-5.4-mini")
    monkeypatch.setenv("FOUNDRY_API_KEY", "dummy")
    # 空文字は「未設定」と同義(.env に実値があっても上書きされない)
    monkeypatch.setenv("FOUNDRY_PROPOSER_MODELS", "")
    monkeypatch.setenv("FOUNDRY_AGGREGATOR_MODEL", "")

    settings = FoundrySettings.from_env()
    assert settings.proposer_models == ()
    assert settings.aggregator_model == "gpt-5.4-mini"


def test_build_agents_wires_personas_offline() -> None:
    pytest.importorskip("agent_framework")
    from mixture_of_agents_maf.agents import build_agents

    agents = build_agents(make_settings())
    assert [p.name for p in agents.proposers] == [name for name, _ in PERSONAS]
    assert agents.aggregator is not None

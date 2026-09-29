"""Offline checks of the provider → MAF client wiring (no network: client
construction does not call the endpoint)."""

import pytest

pytest.importorskip("agent_framework_openai")

from agent_framework.openai import (  # noqa: E402
    OpenAIChatClient,
    OpenAIChatCompletionClient,
)

from agentic_search_maf.config import Config, LlmProviderKind  # noqa: E402
from agentic_search_maf.errors import ConfigError  # noqa: E402
from agentic_search_maf.llm import build_agents, build_chat_client  # noqa: E402


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        # OpenAI-compatible servers (Ollama, Anthropic's compat layer) only
        # implement Chat Completions; OpenAIChatClient is the Responses client.
        (LlmProviderKind.OLLAMA, OpenAIChatCompletionClient),
        (LlmProviderKind.CLAUDE, OpenAIChatCompletionClient),
        (LlmProviderKind.OPENAI, OpenAIChatClient),
    ],
)
def test_provider_selects_client_class(monkeypatch, provider, expected):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    client = build_chat_client(Config.from_env(provider).llm)
    assert type(client) is expected


def test_azure_with_key_uses_responses_client_on_v1_endpoint(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
    config = Config.from_env(LlmProviderKind.AZURE)
    config.llm.model = "gpt-5.4-mini"
    client = build_chat_client(config.llm)
    assert type(client) is OpenAIChatClient
    assert str(client.client.base_url).endswith("/openai/v1/")


def test_azure_requires_endpoint(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    with pytest.raises(ConfigError):
        build_chat_client(Config.from_env(LlmProviderKind.AZURE).llm)


def test_structured_output_is_skipped_for_claude(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    client = build_chat_client(Config.from_env(LlmProviderKind.CLAUDE).llm)
    agents = build_agents(client, "日本語", structured_output=False)
    assert "response_format" not in agents.planner.default_options

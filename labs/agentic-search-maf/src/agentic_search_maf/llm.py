"""LLM provider wiring, replacing ``crates/core/src/llm/``.

The Rust version defined its own ``LlmClient`` trait plus one hand-written
HTTP client per provider (Ollama / Claude / OpenAI). MAF already ships that
abstraction as a chat-client protocol, so this module shrinks to a factory
around the two OpenAI-protocol client classes of ``agent-framework-openai``:

- ``ollama``  → ``OpenAIChatCompletionClient`` on the OpenAI-compatible
  endpoint ``http://localhost:11434/v1`` (Chat Completions: the surface every
  OpenAI-compatible server implements, incl. ``response_format`` since v0.5)
- ``claude``  → ``OpenAIChatCompletionClient`` on Anthropic's OpenAI SDK
  compatibility endpoint, which only implements Chat Completions (no
  Responses API)
- ``openai``  → ``OpenAIChatClient`` (Responses API), SDK defaults
- ``azure``   → ``OpenAIChatClient`` (Responses API) with ``azure_endpoint``
  (Azure OpenAI / Microsoft Foundry Models, ``/openai/v1``;
  ``AZURE_OPENAI_ENDPOINT`` + ``AZURE_OPENAI_API_KEY``, or Entra ID via
  ``DefaultAzureCredential`` when no key is set)

``OpenAIChatClient`` is the *Responses* client since agent-framework 1.10;
Chat Completions lives in ``OpenAIChatCompletionClient``.

Each LLM *role* of the original (planner / extractor / evaluator / reporter)
becomes a stateless ``Agent`` with fixed instructions and, where the
provider supports it, a native structured-output ``response_format``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

from . import prompts
from .config import LlmConfig, LlmProviderKind
from .errors import ConfigError
from .schemas import Evaluation, Extraction, Plan


class SupportsRun(Protocol):
    """The only surface the workflow needs from an agent: ``await run(text)``
    returning an object with ``.text`` and ``.value``. MAF's ``Agent``
    satisfies it; tests substitute scripted fakes (the moral equivalent of
    the Rust ``MockLlm``)."""

    async def run(self, message: str) -> Any: ...


@dataclass
class ResearchAgents:
    """One stateless agent per LLM role of the original design."""

    planner: SupportsRun
    extractor: SupportsRun
    evaluator: SupportsRun
    reporter: SupportsRun


def build_chat_client(config: LlmConfig) -> Any:
    """Build the MAF chat client for the configured provider."""
    from agent_framework.openai import OpenAIChatClient, OpenAIChatCompletionClient

    if config.provider is LlmProviderKind.AZURE:
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        if not endpoint:
            raise ConfigError("provider azure requires AZURE_OPENAI_ENDPOINT")
        api_key = os.environ.get("AZURE_OPENAI_API_KEY") or None
        return OpenAIChatClient(
            model=config.model or None,  # deployment name
            azure_endpoint=endpoint,
            api_key=api_key,
            # MAF does not fall back to Entra ID on its own: without a key it
            # raises SettingNotFoundError, so pass a credential explicitly
            # (Foundry resources often have key auth disabled).
            credential=None if api_key else _entra_credential(),
        )
    if config.provider is LlmProviderKind.OLLAMA:
        return OpenAIChatCompletionClient(
            model=config.model,
            api_key="ollama",  # the endpoint ignores it, the SDK requires it
            base_url=config.base_url,
        )
    if config.provider is LlmProviderKind.CLAUDE:
        return OpenAIChatCompletionClient(
            model=config.model,
            api_key=config.api_key.expose(),
            base_url=config.base_url,
        )
    return OpenAIChatClient(
        model=config.model,
        api_key=config.api_key.expose(),
        base_url=config.base_url or None,
    )


def _entra_credential() -> Any:
    """Keyless Azure auth (``az login`` / managed identity), optional extra."""
    try:
        from azure.identity import DefaultAzureCredential
    except ImportError as exc:
        raise ConfigError(
            "provider azure without AZURE_OPENAI_API_KEY uses Entra ID: "
            "install the 'azure' extra (uv sync --extra azure) and run `az login`"
        ) from exc
    return DefaultAzureCredential()


def build_agents(
    chat_client: Any, report_language: str, structured_output: bool = True
) -> ResearchAgents:
    """Create the four role agents on a shared chat client.

    ``structured_output=False`` skips ``response_format`` for providers whose
    OpenAI-compatibility layer does not honor it (e.g. Anthropic's); the
    prompts still describe the JSON shape and the lenient parser in
    ``schemas.py`` takes over — exactly the Rust code path.
    """
    from agent_framework import Agent, ChatOptions

    def agent(name: str, instructions: str, response_format: Any = None) -> Agent:
        options = (
            ChatOptions(response_format=response_format)
            if structured_output and response_format is not None
            else None
        )
        return Agent(chat_client, instructions=instructions, name=name, default_options=options)

    return ResearchAgents(
        planner=agent("planner", prompts.planner_system(), Plan),
        extractor=agent("extractor", prompts.extractor_system(), Extraction),
        evaluator=agent("evaluator", prompts.evaluator_system(), Evaluation),
        reporter=agent("reporter", prompts.reporter_system(report_language)),
    )


def supports_structured_output(provider: LlmProviderKind) -> bool:
    """Anthropic's OpenAI compatibility endpoint does not honor
    ``response_format``; everything else here does (Ollama since v0.5)."""
    return provider is not LlmProviderKind.CLAUDE

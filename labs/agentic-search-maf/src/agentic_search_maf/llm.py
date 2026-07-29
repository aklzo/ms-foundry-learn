"""LLM provider wiring, replacing ``crates/core/src/llm/``.

The Rust version defined its own ``LlmClient`` trait plus one hand-written
HTTP client per provider (Ollama / Claude / OpenAI). MAF already ships that
abstraction as a chat-client protocol, so this module shrinks to a factory
around a single client class — ``OpenAIChatClient`` (agent-framework 1.10
folded Azure OpenAI into it via the v1 API):

- ``ollama``  → OpenAI-compatible endpoint ``http://localhost:11434/v1``
- ``claude``  → Anthropic's OpenAI SDK compatibility endpoint
- ``openai``  → SDK defaults
- ``azure``   → ``azure_endpoint`` (Azure OpenAI / Microsoft Foundry Models;
  ``AZURE_OPENAI_ENDPOINT`` / ``AZURE_OPENAI_API_KEY``)

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
    from agent_framework.openai import OpenAIChatClient

    if config.provider is LlmProviderKind.AZURE:
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        if not endpoint:
            raise ConfigError("provider azure requires AZURE_OPENAI_ENDPOINT")
        return OpenAIChatClient(
            model=config.model or None,  # deployment name
            azure_endpoint=endpoint,
            api_key=os.environ.get("AZURE_OPENAI_API_KEY") or None,
        )
    if config.provider is LlmProviderKind.OLLAMA:
        return OpenAIChatClient(
            model=config.model,
            api_key="ollama",  # the endpoint ignores it, the SDK requires it
            base_url=config.base_url,
        )
    if config.provider is LlmProviderKind.CLAUDE:
        return OpenAIChatClient(
            model=config.model,
            api_key=config.api_key.expose(),
            base_url=config.base_url,
        )
    return OpenAIChatClient(
        model=config.model,
        api_key=config.api_key.expose(),
        base_url=config.base_url or None,
    )


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

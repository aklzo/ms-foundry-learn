"""Environment-based configuration, ported from ``crates/core/src/config.rs``.

Environment variable names are kept identical to the Rust version (``AGS_*``)
so both tools can share a shell profile. One provider was added: ``azure``
(Azure OpenAI / Microsoft Foundry Models), which is the natural target for
this MAF port.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum

from .errors import ConfigError


class SecretKey:
    """API key wrapper that never appears in logs or debug output."""

    def __init__(self, value: str = "") -> None:
        self._value = value

    def expose(self) -> str:
        return self._value

    def is_empty(self) -> bool:
        return not self._value

    def __repr__(self) -> str:
        return "SecretKey(***)"

    __str__ = __repr__


class LlmProviderKind(str, Enum):
    OLLAMA = "ollama"
    CLAUDE = "claude"
    OPENAI = "openai"
    AZURE = "azure"

    @classmethod
    def parse(cls, value: str) -> LlmProviderKind:
        lowered = value.lower()
        aliases = {"anthropic": cls.CLAUDE, "foundry": cls.AZURE}
        if lowered in aliases:
            return aliases[lowered]
        try:
            return cls(lowered)
        except ValueError:
            raise ConfigError(
                f"unknown LLM provider '{value}' (expected: ollama, claude, openai, azure)"
            ) from None


class SearchProviderKind(str, Enum):
    DUCKDUCKGO = "duckduckgo"
    SEARXNG = "searxng"
    SERPER = "serper"

    @classmethod
    def parse(cls, value: str) -> SearchProviderKind:
        lowered = value.lower()
        if lowered == "ddg":
            return cls.DUCKDUCKGO
        try:
            return cls(lowered)
        except ValueError:
            raise ConfigError(
                f"unknown search provider '{value}' (expected: duckduckgo, searxng, serper)"
            ) from None


@dataclass
class LlmConfig:
    provider: LlmProviderKind
    model: str
    base_url: str
    api_key: SecretKey
    timeout_secs: float


@dataclass
class SearchConfig:
    provider: SearchProviderKind
    searxng_base_url: str
    #: API key for Serper.dev (``SERPER_API_KEY``); required only when the
    #: Serper provider is selected.
    serper_api_key: SecretKey = field(default_factory=SecretKey)


@dataclass
class Limits:
    """Hard limits that bound the agent's autonomy (cost, runtime, memory)."""

    max_iterations: int = 4
    # Matches the planner prompt's "3-6 queries" so none are dropped.
    max_queries_per_iteration: int = 6
    max_results_per_query: int = 8
    max_pages_per_query: int = 3
    max_content_chars: int = 6_000
    fetch_timeout_secs: float = 20.0
    max_response_bytes: int = 2 * 1024 * 1024
    #: How many pages within one query are fetched + extracted concurrently.
    #: Set to 1 for local LLMs (the GPU saturates on a single request, so
    #: concurrency adds no throughput) and higher for cloud APIs.
    max_concurrent_pages: int = 4
    #: Extra attempts for transient fetch/LLM failures (exponential backoff).
    max_retries: int = 2


@dataclass
class Config:
    llm: LlmConfig
    search: SearchConfig
    limits: Limits
    #: Language the final report is written in (``AGS_REPORT_LANGUAGE``).
    report_language: str

    @classmethod
    def from_env(cls, provider_override: LlmProviderKind | None = None) -> Config:
        """Build configuration from environment variables. A provider passed
        on the command line takes precedence over ``AGS_LLM_PROVIDER``."""
        provider = provider_override or LlmProviderKind.parse(
            os.environ.get("AGS_LLM_PROVIDER", "ollama")
        )
        llm = LlmConfig(
            provider=provider,
            model=os.environ.get("AGS_LLM_MODEL", _default_model(provider)),
            base_url=os.environ.get("AGS_LLM_BASE_URL", default_base_url(provider)),
            api_key=SecretKey(_read_api_key(provider)),
            # Local inference is prefill-bound: a 12B model reading the full
            # evaluator digest can legitimately take minutes. APIs stay snappy.
            timeout_secs=900.0 if provider is LlmProviderKind.OLLAMA else 180.0,
        )
        search = SearchConfig(
            provider=SearchProviderKind.parse(os.environ.get("AGS_SEARCH_PROVIDER", "duckduckgo")),
            searxng_base_url=os.environ.get("AGS_SEARXNG_URL", "http://localhost:8080"),
            serper_api_key=SecretKey(os.environ.get("SERPER_API_KEY", "")),
        )
        # Local inference can't parallelize within one GPU; cloud APIs can.
        default_concurrency = 1 if provider is LlmProviderKind.OLLAMA else 4
        limits = Limits(
            max_concurrent_pages=max(1, _env_int("AGS_MAX_CONCURRENT_PAGES", default_concurrency)),
            max_retries=_env_int("AGS_MAX_RETRIES", Limits.max_retries),
        )
        config = cls(
            llm=llm,
            search=search,
            limits=limits,
            report_language=os.environ.get("AGS_REPORT_LANGUAGE", "日本語"),
        )
        config.validate()
        return config

    def validate(self) -> None:
        # Azure resolves credentials through the MAF client's own environment
        # conventions (AZURE_OPENAI_* / Entra ID), so it is not checked here.
        needs_key = self.llm.provider in (LlmProviderKind.CLAUDE, LlmProviderKind.OPENAI)
        if needs_key and self.llm.api_key.is_empty():
            raise ConfigError(
                f"provider {self.llm.provider.value} requires an API key "
                f"({_api_key_env_name(self.llm.provider)})"
            )
        if (
            self.search.provider is SearchProviderKind.SERPER
            and self.search.serper_api_key.is_empty()
        ):
            raise ConfigError("search provider 'serper' requires an API key (SERPER_API_KEY)")


def _default_model(provider: LlmProviderKind) -> str:
    return {
        LlmProviderKind.OLLAMA: "llama3.2:3b",
        LlmProviderKind.CLAUDE: "claude-sonnet-5",
        LlmProviderKind.OPENAI: "gpt-4o-mini",
        # Azure: the "model" is the deployment name; no universal default.
        LlmProviderKind.AZURE: "",
    }[provider]


def default_base_url(provider: LlmProviderKind) -> str:
    """Default API base URL per provider. Ollama and Claude are reached
    through their OpenAI-compatible endpoints (see ``llm.py``)."""
    return {
        LlmProviderKind.OLLAMA: "http://localhost:11434/v1",
        LlmProviderKind.CLAUDE: "https://api.anthropic.com/v1/",
        LlmProviderKind.OPENAI: "",  # SDK default
        LlmProviderKind.AZURE: "",  # AZURE_OPENAI_ENDPOINT
    }[provider]


def _api_key_env_name(provider: LlmProviderKind) -> str:
    return {
        LlmProviderKind.OLLAMA: "",
        LlmProviderKind.CLAUDE: "ANTHROPIC_API_KEY",
        LlmProviderKind.OPENAI: "OPENAI_API_KEY",
        LlmProviderKind.AZURE: "",
    }[provider]


def _read_api_key(provider: LlmProviderKind) -> str:
    name = _api_key_env_name(provider)
    return os.environ.get(name, "") if name else ""


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default

"""Unified error types for the whole package.

The Rust original used a single ``AgentError`` enum with an ``is_retryable``
classifier. Python exceptions map naturally onto a small hierarchy; the
retryability classifier lives in :mod:`retry` because it must also inspect
third-party exceptions (httpx, openai SDK) that we do not wrap.
"""


class AgentError(Exception):
    """Base class for errors raised by this package."""


class ConfigError(AgentError):
    """Invalid or missing configuration."""


class BlockedUrlError(AgentError):
    """URL rejected by the SSRF security policy."""


class LlmResponseError(AgentError):
    """The LLM returned an unusable response (e.g. unparseable JSON)."""


class SearchError(AgentError):
    """A search provider returned an error or unusable payload."""


class FetchError(AgentError):
    """Page retrieval failed for a non-transport reason (bad content type,
    too many redirects)."""

"""Exponential-backoff retry for idempotent async operations.

Used for page fetches and LLM calls, which become more failure-prone once a
query's pages are fetched concurrently (transient timeouts/5xx in a burst).
Only transient transport/server conditions are retried; deterministic
failures (4xx, blocked URL, parse error, bad config) are never retried.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

logger = logging.getLogger(__name__)

#: Base delay in seconds for the first retry; doubles each attempt.
BASE_DELAY = 0.4

#: Exception class names from the openai SDK (used by MAF's OpenAI-compatible
#: chat clients) that represent transient conditions. Matched by name so this
#: module does not import the SDK directly.
_RETRYABLE_SDK_ERRORS = {
    "APITimeoutError",
    "APIConnectionError",
    "RateLimitError",
    "InternalServerError",
}

T = TypeVar("T")


def is_retryable(exc: BaseException) -> bool:
    """Whether retrying the same operation might succeed.

    True only for transient transport/server conditions (timeout, connection
    reset, 5xx, 429).
    """
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status >= 500 or status == 429
    return type(exc).__name__ in _RETRYABLE_SDK_ERRORS


async def with_backoff(
    max_retries: int,
    op: Callable[[], Awaitable[T]],
    *,
    base_delay: float = BASE_DELAY,
) -> T:
    """Run ``op``, retrying up to ``max_retries`` extra times (so
    ``max_retries + 1`` attempts total) while it raises a retryable error,
    sleeping ``base_delay * 2**attempt`` between tries."""
    attempt = 0
    while True:
        try:
            return await op()
        except Exception as exc:
            if attempt >= max_retries or not is_retryable(exc):
                raise
            delay = base_delay * (2**attempt)
            logger.debug(
                "transient error; retrying after backoff (attempt %d): %s",
                attempt + 1,
                exc,
            )
            await asyncio.sleep(delay)
            attempt += 1

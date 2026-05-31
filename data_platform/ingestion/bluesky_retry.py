"""Retry decorator for transient Bluesky API search_posts calls."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import ParamSpec, TypeVar

import httpx
from atproto_client.exceptions import (
    InvokeTimeoutError,
    NetworkError,
    RequestException,
)
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

P = ParamSpec("P")
R = TypeVar("R")
logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 8
INITIAL_DELAY = 2.0
MAX_DELAY = 120.0


def _is_retryable_bluesky_error(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.RequestError)):
        return True
    if isinstance(exc, (InvokeTimeoutError, NetworkError)):
        return True
    if isinstance(exc, RequestException):
        response = exc.response
        if response is None:
            return False
        return response.status_code == 429
    return False


def retry_bluesky_request(
    max_attempts: int = MAX_ATTEMPTS,
    initial_delay: float = INITIAL_DELAY,
    max_delay: float = MAX_DELAY,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Retry Bluesky page fetches on transient HTTP errors and 429 rate limits."""
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential_jitter(initial=initial_delay, max=max_delay),
        retry=retry_if_exception(_is_retryable_bluesky_error),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )

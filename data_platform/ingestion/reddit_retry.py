"""Retry decorator for transient Reddit API calls via PRAW/prawcore."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import ParamSpec, TypeVar

import prawcore.exceptions
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


def _is_retryable_reddit_error(exc: BaseException) -> bool:
    if isinstance(exc, prawcore.exceptions.TooManyRequests):
        return True
    if isinstance(exc, prawcore.exceptions.ServerError):
        return True
    if isinstance(exc, prawcore.exceptions.RequestException):
        response = getattr(exc, "response", None)
        if response is None:
            return True
        return response.status_code in {429, 500, 502, 503, 504}
    return False


def retry_reddit_request(
    max_attempts: int = MAX_ATTEMPTS,
    initial_delay: float = INITIAL_DELAY,
    max_delay: float = MAX_DELAY,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Retry Reddit fetches on transient HTTP errors and 429 rate limits."""
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential_jitter(initial=initial_delay, max=max_delay),
        retry=retry_if_exception(_is_retryable_reddit_error),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )

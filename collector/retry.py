import logging
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

P = ParamSpec("P")
R = TypeVar("R")
logger = logging.getLogger(__name__)

MAX_RETRIES = 3
INITIAL_DELAY = 1.0
MAX_DELAY = 60.0


def retry_llm_completion(
    max_retries: int = MAX_RETRIES,
    initial_delay: float = INITIAL_DELAY,
    max_delay: float = MAX_DELAY,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    return retry(
        stop=stop_after_attempt(max_retries + 1),
        wait=wait_exponential_jitter(initial=initial_delay, max=max_delay),
        retry=retry_if_exception_type(Exception),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )

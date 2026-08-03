"""Retry policy for Iceberg commits.

Mirrors `data_platform/ingestion/bluesky_retry.py`: tenacity, an explicit
predicate for what counts as transient, and `reraise=True` so the caller sees the
original error rather than a `RetryError` wrapper.
"""

import logging
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from botocore.exceptions import BotoCoreError, ClientError
from pyiceberg.exceptions import (
    CommitFailedException,
    NoSuchTableError,
    ServerError,
)
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from bluesky_ingestion_jetstream.aws.constants import (
    COMMIT_INITIAL_DELAY_SECONDS,
    COMMIT_MAX_ATTEMPTS,
    COMMIT_MAX_DELAY_SECONDS,
)

P = ParamSpec("P")
R = TypeVar("R")
logger = logging.getLogger(__name__)

# A commit that failed for one of these reasons will fail again in a second's
# time. Retrying a schema mismatch just delays the dead letter by the length of
# the backoff, and hides a code bug behind two pointless round trips.
NON_RETRYABLE = (ValueError, TypeError, NoSuchTableError)


def is_retryable_commit_error(error: BaseException) -> bool:
    """Whether re-issuing the same commit could plausibly succeed.

    Deliberately a denylist rather than an allowlist. The commit path spans
    PyArrow's S3 client, botocore, and PyIceberg, and an unrecognised error from
    that surface is far more likely to be a transport failure than a logic bug --
    so the default is to retry, and only the known-permanent cases opt out.
    """

    if isinstance(error, NON_RETRYABLE):
        return False
    return isinstance(
        error, CommitFailedException | ServerError | ClientError | BotoCoreError | OSError
    )


def retry_iceberg_commit(
    max_attempts: int = COMMIT_MAX_ATTEMPTS,
    initial_delay: float = COMMIT_INITIAL_DELAY_SECONDS,
    max_delay: float = COMMIT_MAX_DELAY_SECONDS,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Retry a commit on transient failures, with jittered exponential backoff."""

    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential_jitter(initial=initial_delay, max=max_delay),
        retry=retry_if_exception(is_retryable_commit_error),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )

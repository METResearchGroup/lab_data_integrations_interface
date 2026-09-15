import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from bluesky_backfill_app.fetch_repos.constants import (
    GET_REPO_DEADLINE_SECONDS,
    GET_REPO_MAX_ATTEMPTS,
    GET_REPO_READ_CHUNK_BYTES,
    GET_REPO_TIMEOUT_SECONDS,
    GET_REPO_URL,
)
from bluesky_backfill_app.fetch_repos.network.errors import TRANSPORT_ERRORS, XrpcError
from bluesky_backfill_app.gather_users.constants import RETRYABLE_STATUS_CODES
from bluesky_backfill_app.gather_users.network.list_repos import backoff_seconds, retry_delay

logger = logging.getLogger(__name__)

UrlOpen = Callable[..., Any]


def build_url(did: str) -> str:
    return f"{GET_REPO_URL}?{urllib.parse.urlencode({'did': did})}"


def read_body(response: Any, deadline: float, clock: Callable[[], float]) -> bytes:
    chunks = []
    while chunk := response.read(GET_REPO_READ_CHUNK_BYTES):
        chunks.append(chunk)
        if clock() > deadline:
            raise TimeoutError("getRepo download passed its deadline")
    return b"".join(chunks)


def fetch_repo(
    did: str,
    urlopen: UrlOpen = urllib.request.urlopen,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> bytes:
    url = build_url(did)
    deadline = clock() + GET_REPO_DEADLINE_SECONDS
    last_attempt = GET_REPO_MAX_ATTEMPTS - 1

    def can_retry(attempt: int, delay: float) -> bool:
        return attempt < last_attempt and clock() + delay < deadline

    for attempt in range(GET_REPO_MAX_ATTEMPTS):
        try:
            with urlopen(url, timeout=GET_REPO_TIMEOUT_SECONDS) as response:
                return read_body(response, deadline, clock)
        except urllib.error.HTTPError as error:
            xrpc_error = XrpcError.from_http_error(error)
            delay = retry_delay(error, attempt)
            if error.code not in RETRYABLE_STATUS_CODES or not can_retry(attempt, delay):
                raise xrpc_error from error
            logger.warning("getRepo %s %d, retrying in %.1fs", did, error.code, delay)
            sleep(delay)
        except TRANSPORT_ERRORS as error:
            delay = backoff_seconds(attempt)
            if not can_retry(attempt, delay):
                raise
            logger.warning("getRepo %s %r, retrying in %.1fs", did, error, delay)
            sleep(delay)

    raise RuntimeError(f"getRepo exhausted {GET_REPO_MAX_ATTEMPTS} attempts")

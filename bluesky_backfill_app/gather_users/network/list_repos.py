import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from bluesky_backfill_app.gather_users.constants import (
    INITIAL_BACKOFF_SECONDS,
    LIST_REPOS_MAX_ATTEMPTS,
    LIST_REPOS_PAGE_SIZE,
    LIST_REPOS_TIMEOUT_SECONDS,
    LIST_REPOS_URL,
    MAX_BACKOFF_SECONDS,
    RETRYABLE_STATUS_CODES,
)

logger = logging.getLogger(__name__)

UrlOpen = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class RepoPage:
    dids: list[str]
    cursor: str | None


def backoff_seconds(attempt: int) -> float:
    return min(INITIAL_BACKOFF_SECONDS * 2**attempt, MAX_BACKOFF_SECONDS)


def retry_delay(error: urllib.error.HTTPError, attempt: int) -> float:
    """Retry-After when the relay sends a numeric one, else the backoff."""

    header = error.headers.get("Retry-After") if error.headers else None
    if header:
        try:
            return min(float(header), MAX_BACKOFF_SECONDS)
        except ValueError:
            pass
    return backoff_seconds(attempt)


def build_url(cursor: str | None, page_size: int) -> str:
    params: dict[str, Any] = {"limit": page_size}
    if cursor:
        params["cursor"] = cursor
    return f"{LIST_REPOS_URL}?{urllib.parse.urlencode(params)}"


def is_active(repo: dict[str, Any]) -> bool:
    """Whether the repo is fetchable. Absent `active` counts as active."""

    return repo.get("active") is not False


def parse_page(payload: dict[str, Any]) -> RepoPage:
    repos = payload.get("repos")
    if not isinstance(repos, list):
        repos = []
    dids = [
        repo["did"]
        for repo in repos
        if isinstance(repo, dict) and repo.get("did") and is_active(repo)
    ]
    cursor = payload.get("cursor")
    return RepoPage(dids=dids, cursor=cursor if isinstance(cursor, str) else None)


def fetch_page(
    cursor: str | None,
    page_size: int = LIST_REPOS_PAGE_SIZE,
    urlopen: UrlOpen = urllib.request.urlopen,
    sleep: Callable[[float], None] = time.sleep,
) -> RepoPage:
    """One page, retrying rate limits and transient failures."""

    url = build_url(cursor, page_size)
    last_attempt = LIST_REPOS_MAX_ATTEMPTS - 1

    for attempt in range(LIST_REPOS_MAX_ATTEMPTS):
        try:
            with urlopen(url, timeout=LIST_REPOS_TIMEOUT_SECONDS) as response:
                return parse_page(json.loads(response.read().decode("utf-8")))
        except urllib.error.HTTPError as error:
            if error.code not in RETRYABLE_STATUS_CODES or attempt == last_attempt:
                raise
            delay = retry_delay(error, attempt)
            logger.warning("listRepos %d, retrying in %.1fs", error.code, delay)
            sleep(delay)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            if attempt == last_attempt:
                raise
            delay = backoff_seconds(attempt)
            logger.warning("listRepos %s, retrying in %.1fs", error, delay)
            sleep(delay)

    raise RuntimeError(f"listRepos exhausted {LIST_REPOS_MAX_ATTEMPTS} attempts")


def iter_pages(cursor: str | None) -> Iterator[RepoPage]:
    """Pages from `cursor` onward, stopping when the relay returns no cursor."""

    while True:
        page = fetch_page(cursor)
        yield page
        if not page.cursor:
            return
        cursor = page.cursor

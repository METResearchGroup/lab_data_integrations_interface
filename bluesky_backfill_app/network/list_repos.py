import logging
from collections.abc import Iterator
from dataclasses import dataclass

logger = logging.getLogger(__name__)

LIST_REPOS_URL = "https://relay1.us-east.bsky.network/xrpc/com.atproto.sync.listRepos"
LIST_REPOS_PAGE_SIZE = 1000


@dataclass(frozen=True, slots=True)
class RepoPage:
    dids: list[str]
    cursor: str | None


def fetch_page(cursor: str | None, page_size: int = LIST_REPOS_PAGE_SIZE) -> RepoPage:
    """One page, retrying rate limits and transient failures."""

    raise NotImplementedError


def iter_pages(cursor: str | None) -> Iterator[RepoPage]:
    """Pages from `cursor` onward, stopping when the relay returns no cursor."""

    raise NotImplementedError

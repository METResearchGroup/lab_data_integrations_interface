"""Author-feed helpers for listing AOC post URIs."""

from typing import Any


def resolve_did(client: Any, handle: str) -> str:
    """Resolve a Bluesky handle to its DID.

    Parameters
    ----------
    client
        Authenticated or public AppView client.
    handle
        Account handle such as ``aoc.bsky.social``.

    Returns
    -------
    str
        Decentralized identifier for the account.
    """
    raise NotImplementedError


def fetch_latest_post_uris(client: Any, actor: str, min_posts: int) -> list[str]:
    """Return at least ``min_posts`` latest post URIs authored by ``actor``.

    Parameters
    ----------
    client
        Public AppView client.
    actor
        Account DID used as the author-feed actor.
    min_posts
        Minimum number of authored post URIs required.

    Returns
    -------
    list[str]
        Post at-URIs in AppView feed order (newest first).

    Raises
    ------
    ValueError
        When the feed is exhausted before ``min_posts`` URIs are collected.
    """
    raise NotImplementedError

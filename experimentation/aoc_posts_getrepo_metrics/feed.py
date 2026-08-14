"""Author-feed helpers for listing AOC post URIs."""

from typing import Any

from experimentation.aoc_posts_getrepo_metrics.constants import AUTHOR_FEED_PAGE_SIZE


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
    profile = client.app.bsky.actor.get_profile({"actor": handle})
    return profile.did


def fetch_latest_post_uris(client: Any, actor: str, min_posts: int) -> list[str]:
    """Return at least ``min_posts`` latest post URIs authored by ``actor``.

    Pages ``getAuthorFeed``, keeps only posts whose author DID matches
    ``actor``, and stops once enough unique URIs are collected.

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
        Unique post at-URIs in AppView feed order (newest first).

    Raises
    ------
    ValueError
        When the feed is exhausted before ``min_posts`` URIs are collected.
    """
    uris: list[str] = []
    seen_uris: set[str] = set()
    seen_cursors: set[str] = set()
    cursor: str | None = None

    while len(uris) < min_posts:
        if cursor is not None:
            if cursor in seen_cursors:
                break
            seen_cursors.add(cursor)

        params: dict[str, Any] = {
            "actor": actor,
            "limit": AUTHOR_FEED_PAGE_SIZE,
        }
        if cursor:
            params["cursor"] = cursor

        response = client.app.bsky.feed.get_author_feed(params)
        page_uris = [item.post.uri for item in response.feed if item.post.author.did == actor]
        if not page_uris and not getattr(response, "cursor", None):
            break

        for uri in page_uris:
            if uri in seen_uris:
                continue
            seen_uris.add(uri)
            uris.append(uri)
            if len(uris) >= min_posts:
                break

        cursor = getattr(response, "cursor", None)
        if not cursor:
            break

    if len(uris) < min_posts:
        raise ValueError(
            f"Author feed returned {len(uris)} posts authored by {actor}; "
            f"needed at least {min_posts}"
        )
    return uris

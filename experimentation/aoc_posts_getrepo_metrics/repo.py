"""Relay getRepo helpers for indexing AOC post records."""

from typing import Any


def fetch_and_index_posts(relay_client: Any, did: str) -> dict[str, dict]:
    """Download one repo export and index ``app.bsky.feed.post`` records by URI.

    Parameters
    ----------
    relay_client
        Unauthenticated relay client.
    did
        Account DID whose repo should be exported.

    Returns
    -------
    dict[str, dict]
        Mapping of post at-URI to decoded post record.

    Raises
    ------
    ValueError
        When the decoded repo DID does not match ``did``.
    """
    raise NotImplementedError

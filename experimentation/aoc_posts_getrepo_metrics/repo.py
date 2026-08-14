"""Relay getRepo helpers for indexing AOC post records."""

from typing import Any

from experimentation.aoc_followers_backfill.mst import decode_repo
from experimentation.aoc_posts_getrepo_metrics.constants import POST_COLLECTION


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
    repo_bytes = relay_client.com.atproto.sync.get_repo({"did": did})
    repo_did, records = decode_repo(repo_bytes)
    if repo_did != did:
        raise ValueError(f"getRepo DID mismatch: expected {did}, got {repo_did}")
    return {
        uri: record for uri, record in records.items() if record.get("$type") == POST_COLLECTION
    }

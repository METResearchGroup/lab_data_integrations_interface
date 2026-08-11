"""Derive getRepo-only metric rows for collected post URIs."""


def derive_row(post_uri: str, record: dict | None) -> dict:
    """Build one metrics row from a post URI and optional repo record.

    Parameters
    ----------
    post_uri
        Post at-URI from the author feed.
    record
        Decoded ``app.bsky.feed.post`` record, or ``None`` when absent.

    Returns
    -------
    dict
        Row keyed by ``CSV_FIELDNAMES``. Engagement counts are always ``None``.
    """
    raise NotImplementedError


def derive_rows(post_uris: list[str], posts_by_uri: dict[str, dict]) -> list[dict]:
    """Build metrics rows for each post URI, preserving input order.

    Parameters
    ----------
    post_uris
        Post at-URIs in the desired output order.
    posts_by_uri
        Repo post index from ``fetch_and_index_posts``.

    Returns
    -------
    list[dict]
        One metrics row per URI.
    """
    raise NotImplementedError

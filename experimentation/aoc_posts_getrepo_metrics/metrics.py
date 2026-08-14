"""Derive getRepo-only metric rows for collected post URIs."""

from experimentation.aoc_posts_getrepo_metrics.constants import (
    CSV_FIELDNAMES,
    DELETED_STATUS_UNKNOWN,
    EMBED_IMAGES,
    EMBED_RECORD_WITH_MEDIA,
    EMBED_VIDEO,
    PostType,
)

_ENGAGEMENT_FIELDS = (
    "like_count",
    "reply_count",
    "repost_count",
    "quote_count",
    "save_count",
    "counts_read_at",
)


def _embed_media_type(embed: dict | None) -> str | None:
    """Return the images/video embed type, including nested recordWithMedia."""
    if not embed:
        return None
    embed_type = embed.get("$type")
    if embed_type in {EMBED_IMAGES, EMBED_VIDEO}:
        return embed_type
    if embed_type == EMBED_RECORD_WITH_MEDIA:
        media = embed.get("media") or {}
        media_type = media.get("$type")
        if media_type in {EMBED_IMAGES, EMBED_VIDEO}:
            return media_type
    return None


def _post_type(record: dict) -> str:
    if "reply" in record and record["reply"] is not None:
        return PostType.REPLY.value
    return PostType.ORIGINAL.value


def derive_row(post_uri: str, record: dict | None) -> dict:
    """Build one metrics row from a post URI and optional repo record.

    Engagement counts stay ``None`` here. Fill them later with AppView
    ``getPosts`` enrichment. Deletion status is always ``unknown``.

    Parameters
    ----------
    post_uri
        Post at-URI from the author feed.
    record
        Decoded ``app.bsky.feed.post`` record, or ``None`` when absent.

    Returns
    -------
    dict
        Row keyed by ``CSV_FIELDNAMES``.
    """
    row = {field: None for field in CSV_FIELDNAMES}
    row["post_uri"] = post_uri
    row["post_rkey"] = post_uri.rsplit("/", 1)[-1]
    row["deleted"] = DELETED_STATUS_UNKNOWN
    row["deleted_at"] = None
    for field in _ENGAGEMENT_FIELDS:
        row[field] = None

    if record is None:
        return row

    media_type = _embed_media_type(record.get("embed"))
    row["created_at"] = record.get("createdAt")
    row["post_type"] = _post_type(record)
    row["has_image"] = media_type == EMBED_IMAGES
    row["has_video"] = media_type == EMBED_VIDEO
    row["langs"] = ";".join(record.get("langs") or [])
    return row


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
    return [derive_row(uri, posts_by_uri.get(uri)) for uri in post_uris]

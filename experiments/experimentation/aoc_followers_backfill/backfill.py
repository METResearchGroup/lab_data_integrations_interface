from datetime import UTC, datetime, timedelta

from atproto import Client

from experimentation.aoc_followers_backfill.client import create_relay_client
from experimentation.aoc_followers_backfill.constants import DAYS_BACK, TARGET_COLLECTIONS
from experimentation.aoc_followers_backfill.mst import decode_repo


def _parse_bsky_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _extract_mentioned_dids(facets: list[dict]) -> str:
    dids = [
        feature["did"]
        for facet in facets
        for feature in facet.get("features", [])
        if feature.get("$type") == "app.bsky.richtext.facet#mention"
    ]
    return ";".join(dids)


def _extract_linked_uris(facets: list[dict]) -> str:
    uris = [
        feature["uri"]
        for facet in facets
        for feature in facet.get("features", [])
        if feature.get("$type") == "app.bsky.richtext.facet#link"
    ]
    return ";".join(uris)


def _extract_quoted_post_uri(embed: dict | None) -> str | None:
    if not embed:
        return None
    embed_type = embed.get("$type")
    if embed_type == "app.bsky.embed.record":
        return embed.get("record", {}).get("uri")
    if embed_type == "app.bsky.embed.recordWithMedia":
        return embed.get("record", {}).get("record", {}).get("uri")
    return None


def _build_post_row(uri: str, record: dict, handle: str, did: str) -> dict:
    reply = record.get("reply")
    embed = record.get("embed")
    embed_type = embed.get("$type", "").rsplit(".", 1)[-1] if embed else None
    langs = record.get("langs") or []
    return {
        "author_handle": handle,
        "author_did": did,
        "uri": uri,
        "created_at": record.get("createdAt"),
        "text": record.get("text", ""),
        "is_reply": reply is not None,
        "reply_parent_uri": reply["parent"]["uri"] if reply else None,
        "reply_root_uri": reply["root"]["uri"] if reply else None,
        "langs": ";".join(langs),
        "embed_type": embed_type,
        "quoted_post_uri": _extract_quoted_post_uri(embed),
        "mentioned_dids": _extract_mentioned_dids(record.get("facets") or []),
        "linked_uris": _extract_linked_uris(record.get("facets") or []),
    }


def _build_like_or_repost_row(uri: str, record: dict, handle: str, did: str) -> dict:
    subject = record.get("subject") or {}
    return {
        "author_handle": handle,
        "author_did": did,
        "uri": uri,
        "created_at": record.get("createdAt"),
        "subject_uri": subject.get("uri"),
        "subject_cid": subject.get("cid"),
    }


def _build_follow_row(uri: str, record: dict, handle: str, did: str) -> dict:
    return {
        "author_handle": handle,
        "author_did": did,
        "uri": uri,
        "created_at": record.get("createdAt"),
        "followed_did": record.get("subject"),
    }


_ROW_BUILDERS = {
    "app.bsky.feed.post": _build_post_row,
    "app.bsky.feed.like": _build_like_or_repost_row,
    "app.bsky.feed.repost": _build_like_or_repost_row,
    "app.bsky.graph.follow": _build_follow_row,
}


def backfill_user(
    user: dict, relay_client: Client | None = None, days_back: int = DAYS_BACK
) -> tuple[dict[str, list[dict]], str | None]:
    """Fetches this user's repo via getRepo, decodes it, and returns rows
    from the last `days_back` days, bucketed by output file name ("posts",
    "likes", "reposts", "follows").

    Returns (rows_by_type, error) - error is None on success, otherwise a
    short description of what failed (rows_by_type will be empty buckets).
    """
    if relay_client is None:
        relay_client = create_relay_client()

    rows_by_type: dict[str, list[dict]] = {name: [] for name in set(TARGET_COLLECTIONS.values())}

    try:
        repo_bytes = relay_client.com.atproto.sync.get_repo({"did": user["did"]})
    except Exception as e:
        return rows_by_type, f"getRepo failed: {e}"

    try:
        _, records = decode_repo(repo_bytes)
    except Exception as e:
        return rows_by_type, f"CAR/MST decode failed: {e}"

    cutoff = datetime.now(UTC) - timedelta(days=days_back)

    for uri, record in records.items():
        collection = record.get("$type")
        if collection is None:
            continue
        output_name = TARGET_COLLECTIONS.get(collection)
        if output_name is None:
            continue

        created_at = record.get("createdAt")
        if not created_at:
            continue
        try:
            created_dt = _parse_bsky_datetime(created_at)
        except ValueError:
            continue
        if created_dt < cutoff:
            continue

        row = _ROW_BUILDERS[collection](uri, record, user["handle"], user["did"])
        rows_by_type[output_name].append(row)

    return rows_by_type, None

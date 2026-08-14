"""Classify decoded repo records into typed rows for derivation and raw dumps."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class PostRow:
    """One feed post record from a user repo."""

    uri: str
    created_at: str | None
    text: str
    is_reply: bool
    reply_parent_uri: str | None
    reply_root_uri: str | None
    langs: str
    embed_type: str | None
    quoted_post_uri: str | None
    mentioned_dids: str
    linked_uris: str


@dataclass(frozen=True)
class LikeOrRepostRow:
    """One like or repost record."""

    uri: str
    created_at: str | None
    subject_uri: str | None
    subject_cid: str | None


@dataclass(frozen=True)
class FollowRow:
    """One outbound follow record still present in the repo."""

    uri: str
    created_at: str | None
    followed_did: str | None


@dataclass(frozen=True)
class ProfileRecord:
    """Current ``app.bsky.actor.profile`` record, when present."""

    display_name: str | None
    description: str | None
    created_at: str | None


def parse_bsky_datetime(value: str) -> datetime:
    """Parse a Bluesky ISO-8601 timestamp into an aware datetime."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def extract_quoted_post_uri(embed: dict | None) -> str | None:
    """Return the quoted post URI from a quote or quote-with-media embed."""
    if not embed:
        return None
    embed_type = embed.get("$type")
    if embed_type == "app.bsky.embed.record":
        return embed.get("record", {}).get("uri")
    if embed_type == "app.bsky.embed.recordWithMedia":
        return embed.get("record", {}).get("record", {}).get("uri")
    return None


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


def build_post_row(uri: str, record: dict[str, Any]) -> PostRow:
    """Map a post record dict into a ``PostRow``."""
    reply = record.get("reply")
    embed = record.get("embed")
    embed_type = embed.get("$type", "").rsplit(".", 1)[-1] if embed else None
    langs = record.get("langs") or []
    return PostRow(
        uri=uri,
        created_at=record.get("createdAt"),
        text=record.get("text", ""),
        is_reply=reply is not None,
        reply_parent_uri=reply["parent"]["uri"] if reply else None,
        reply_root_uri=reply["root"]["uri"] if reply else None,
        langs=";".join(langs),
        embed_type=embed_type,
        quoted_post_uri=extract_quoted_post_uri(embed),
        mentioned_dids=_extract_mentioned_dids(record.get("facets") or []),
        linked_uris=_extract_linked_uris(record.get("facets") or []),
    )


def build_like_or_repost_row(uri: str, record: dict[str, Any]) -> LikeOrRepostRow:
    """Map a like or repost record dict into a ``LikeOrRepostRow``."""
    subject = record.get("subject") or {}
    return LikeOrRepostRow(
        uri=uri,
        created_at=record.get("createdAt"),
        subject_uri=subject.get("uri"),
        subject_cid=subject.get("cid"),
    )


def build_follow_row(uri: str, record: dict[str, Any]) -> FollowRow:
    """Map a follow record dict into a ``FollowRow``."""
    return FollowRow(
        uri=uri,
        created_at=record.get("createdAt"),
        followed_did=record.get("subject"),
    )


def build_profile_record(record: dict[str, Any]) -> ProfileRecord:
    """Map a profile record dict into a ``ProfileRecord``."""
    return ProfileRecord(
        display_name=record.get("displayName"),
        description=record.get("description"),
        created_at=record.get("createdAt"),
    )


def created_at_in_window(
    created_at: str | None, window_start: datetime, window_end: datetime
) -> bool:
    """Return True when ``created_at`` is timezone-aware and inside the window."""
    if not created_at:
        return False
    try:
        created_dt = parse_bsky_datetime(created_at)
    except ValueError:
        return False
    if created_dt.tzinfo is None:
        return False
    return window_start <= created_dt <= window_end


def filter_rows_by_window(rows: list, window_start: datetime, window_end: datetime) -> list:
    """Keep rows whose ``created_at`` falls inside the trailing window."""
    return [row for row in rows if created_at_in_window(row.created_at, window_start, window_end)]

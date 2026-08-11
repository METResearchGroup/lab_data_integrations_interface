"""Fetch and decode cohort repos via relay getRepo and imported MST helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from atproto import Client

from experimentation.aoc_followers_backfill.mst import decode_repo
from experiments.aoc_getrepo_derived_stats_2026_08_11.constants import (
    PROFILE_COLLECTION,
    TARGET_COLLECTIONS,
)
from experiments.aoc_getrepo_derived_stats_2026_08_11.discovery import CohortMember
from experiments.aoc_getrepo_derived_stats_2026_08_11.records import (
    FollowRow,
    LikeOrRepostRow,
    PostRow,
    ProfileRecord,
    build_follow_row,
    build_like_or_repost_row,
    build_post_row,
    build_profile_record,
)


@dataclass
class RepoBundle:
    """Decoded collections for one cohort member."""

    did: str
    handle: str
    posts: list[PostRow] = field(default_factory=list)
    likes: list[LikeOrRepostRow] = field(default_factory=list)
    reposts: list[LikeOrRepostRow] = field(default_factory=list)
    follows: list[FollowRow] = field(default_factory=list)
    profile: ProfileRecord | None = None
    error: str | None = None


def _empty_bundle(member: CohortMember, error: str | None = None) -> RepoBundle:
    return RepoBundle(did=member.did, handle=member.handle, error=error)


def classify_records(
    records: dict[str, dict[str, Any]],
) -> tuple[
    list[PostRow],
    list[LikeOrRepostRow],
    list[LikeOrRepostRow],
    list[FollowRow],
    ProfileRecord | None,
]:
    """Split a decoded URI→record map into typed collection lists."""
    posts: list[PostRow] = []
    likes: list[LikeOrRepostRow] = []
    reposts: list[LikeOrRepostRow] = []
    follows: list[FollowRow] = []
    profile: ProfileRecord | None = None

    for uri, record in records.items():
        collection = record.get("$type")
        if collection == PROFILE_COLLECTION:
            profile = build_profile_record(record)
            continue
        output_name = TARGET_COLLECTIONS.get(collection)
        if output_name == "posts":
            posts.append(build_post_row(uri, record))
        elif output_name == "likes":
            likes.append(build_like_or_repost_row(uri, record))
        elif output_name == "reposts":
            reposts.append(build_like_or_repost_row(uri, record))
        elif output_name == "follows":
            follows.append(build_follow_row(uri, record))

    return posts, likes, reposts, follows, profile


def fetch_one_repo(member: CohortMember, relay_client: Client) -> RepoBundle:
    """Download and decode one member's repo from the relay.

    Parameters
    ----------
    member
        Cohort member identity.
    relay_client
        Unauthenticated client pointed at the relay.

    Returns
    -------
    RepoBundle
        Typed collections on success, or empty collections with ``error`` set.
    """
    try:
        repo_bytes = relay_client.com.atproto.sync.get_repo({"did": member.did})
    except Exception as exc:
        return _empty_bundle(member, error=f"getRepo failed: {exc}")

    try:
        _, records = decode_repo(repo_bytes)
    except Exception as exc:
        return _empty_bundle(member, error=f"CAR/MST decode failed: {exc}")

    try:
        posts, likes, reposts, follows, profile = classify_records(records)
    except Exception as exc:
        return _empty_bundle(member, error=f"record classification failed: {exc}")

    return RepoBundle(
        did=member.did,
        handle=member.handle,
        posts=posts,
        likes=likes,
        reposts=reposts,
        follows=follows,
        profile=profile,
        error=None,
    )


def fetch_cohort_repos(
    members: tuple[CohortMember, ...] | list[CohortMember],
    relay_client: Client,
) -> list[RepoBundle]:
    """Fetch repos for every cohort member, isolating per-DID failures."""
    return [fetch_one_repo(member, relay_client) for member in members]

"""Derive per-member 6-month stats from repo bundles with honest nulls."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from experiments.aoc_getrepo_derived_stats_2026_08_11.discovery import CohortMember
from experiments.aoc_getrepo_derived_stats_2026_08_11.fetch_repos import RepoBundle
from experiments.aoc_getrepo_derived_stats_2026_08_11.records import (
    FollowRow,
    PostRow,
    created_at_in_window,
    filter_rows_by_window,
)
from experiments.aoc_getrepo_derived_stats_2026_08_11.schemas import (
    DERIVED_STAT_KEYS,
    empty_derived_stats_shell,
)


def _original_posts(
    posts: list[PostRow], window_start: datetime, window_end: datetime
) -> list[dict[str, Any]]:
    return [
        {"uri": post.uri, "created_at": post.created_at, "text": post.text}
        for post in filter_rows_by_window(posts, window_start, window_end)
        if not post.is_reply
    ]


def _liked_or_reposted(rows, window_start: datetime, window_end: datetime) -> list[dict[str, Any]]:
    return [
        {
            "uri": row.uri,
            "created_at": row.created_at,
            "subject_uri": row.subject_uri,
            "subject_cid": row.subject_cid,
        }
        for row in filter_rows_by_window(rows, window_start, window_end)
    ]


def _quoted_posts(
    posts: list[PostRow], window_start: datetime, window_end: datetime
) -> list[dict[str, Any]]:
    return [
        {
            "uri": post.uri,
            "created_at": post.created_at,
            "text": post.text,
            "quoted_post_uri": post.quoted_post_uri,
            "quoted_post_body": None,
        }
        for post in filter_rows_by_window(posts, window_start, window_end)
        if post.quoted_post_uri
    ]


def _replied_posts(
    posts: list[PostRow], window_start: datetime, window_end: datetime
) -> list[dict[str, Any]]:
    return [
        {
            "uri": post.uri,
            "created_at": post.created_at,
            "text": post.text,
            "reply_parent_uri": post.reply_parent_uri,
            "reply_root_uri": post.reply_root_uri,
            "parent_post_body": None,
        }
        for post in filter_rows_by_window(posts, window_start, window_end)
        if post.is_reply
    ]


def _follow_actions(
    follows: list[FollowRow], window_start: datetime, window_end: datetime
) -> list[dict[str, Any]]:
    return [
        {
            "uri": follow.uri,
            "created_at": follow.created_at,
            "followed_did": follow.followed_did,
        }
        for follow in follows
        if created_at_in_window(follow.created_at, window_start, window_end)
    ]


def _cohort_followees(follows: list[FollowRow], cohort_dids: set[str]) -> list[str]:
    return sorted(
        {
            follow.followed_did
            for follow in follows
            if follow.followed_did and follow.followed_did in cohort_dids
        }
    )


def _cohort_follower_map(
    bundles_by_did: dict[str, RepoBundle], cohort_dids: set[str]
) -> dict[str, list[str]]:
    """Map each DID to cohort members who still follow them."""
    followers: dict[str, set[str]] = {did: set() for did in cohort_dids}
    for source_did, bundle in bundles_by_did.items():
        if bundle.error is not None:
            continue
        for follow in bundle.follows:
            target = follow.followed_did
            if target in cohort_dids and target != source_did:
                followers[target].add(source_did)
    return {did: sorted(sources) for did, sources in followers.items()}


def _derive_one(
    member: CohortMember,
    bundle: RepoBundle,
    window_start: datetime,
    window_end: datetime,
    cohort_dids: set[str],
    cohort_followers: list[str],
) -> dict[str, Any]:
    window_start_iso = window_start.isoformat()
    window_end_iso = window_end.isoformat()
    shell = empty_derived_stats_shell(
        did=member.did,
        handle=member.handle or None,
        window_start=window_start_iso,
        window_end=window_end_iso,
    )
    shell["followers_count"] = member.followers_count
    shell["cohort_followers"] = cohort_followers

    if bundle.error is not None:
        return shell

    profile = bundle.profile
    if profile is not None:
        shell["display_name"] = profile.display_name
        shell["bio"] = profile.description
        # Profile record createdAt only; never infer from earliest post.
        shell["account_created_at"] = profile.created_at

    shell["original_posts"] = _original_posts(bundle.posts, window_start, window_end)
    shell["liked_posts"] = _liked_or_reposted(bundle.likes, window_start, window_end)
    shell["reposted_posts"] = _liked_or_reposted(bundle.reposts, window_start, window_end)
    shell["quoted_posts"] = _quoted_posts(bundle.posts, window_start, window_end)
    shell["replied_posts"] = _replied_posts(bundle.posts, window_start, window_end)
    shell["cohort_followees"] = _cohort_followees(bundle.follows, cohort_dids)
    shell["followees_count"] = len(bundle.follows)
    shell["follow_actions"] = _follow_actions(bundle.follows, window_start, window_end)
    return shell


def derive_stats(
    members: tuple[CohortMember, ...] | list[CohortMember],
    bundles: list[RepoBundle],
    window_start: datetime,
    window_end: datetime,
) -> list[dict[str, Any]]:
    """Build derived-stat objects for each cohort member.

    Quote and reply target bodies are always None. Saved posts and unfollow
    actions are always None. Account creation is taken only from the profile
    record when present.

    Parameters
    ----------
    members
        Cohort members in display order (seed first).
    bundles
        Repo bundles aligned to the same members by DID.
    window_start, window_end
        Trailing activity window bounds.

    Returns
    -------
    list[dict[str, Any]]
        One object per member with keys in ``DERIVED_STAT_KEYS`` order.
    """
    bundles_by_did = {bundle.did: bundle for bundle in bundles}
    cohort_dids = {member.did for member in members}
    follower_map = _cohort_follower_map(bundles_by_did, cohort_dids)

    results: list[dict[str, Any]] = []
    for member in members:
        bundle = bundles_by_did.get(member.did)
        if bundle is None:
            bundle = RepoBundle(
                did=member.did,
                handle=member.handle,
                error="missing repo bundle",
            )
        row = _derive_one(
            member,
            bundle,
            window_start,
            window_end,
            cohort_dids,
            follower_map.get(member.did, []),
        )
        assert list(row.keys()) == list(DERIVED_STAT_KEYS)
        results.append(row)
    return results

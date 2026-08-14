"""Derived-stat field contracts and null sentinels for unknowable fields."""

from __future__ import annotations

from typing import Any

DERIVED_STAT_KEYS: tuple[str, ...] = (
    "did",
    "handle",
    "display_name",
    "bio",
    "account_created_at",
    "window_start",
    "window_end",
    "original_posts",
    "liked_posts",
    "reposted_posts",
    "quoted_posts",
    "replied_posts",
    "saved_posts",
    "cohort_followers",
    "cohort_followees",
    "followers_count",
    "followees_count",
    "follow_actions",
    "unfollow_actions",
)

# Fields that the repo snapshot cannot observe; always None, never [].
UNKNOWABLE_LIST_FIELDS: tuple[str, ...] = ("saved_posts", "unfollow_actions")

# Activity / graph lists that may honestly be empty when observed.
KNOWABLE_LIST_FIELDS: tuple[str, ...] = (
    "original_posts",
    "liked_posts",
    "reposted_posts",
    "quoted_posts",
    "replied_posts",
    "cohort_followers",
    "cohort_followees",
    "follow_actions",
)

SCALAR_CSV_FIELDS: tuple[str, ...] = (
    "did",
    "handle",
    "display_name",
    "bio",
    "account_created_at",
    "window_start",
    "window_end",
    "followers_count",
    "followees_count",
    "saved_posts",
    "unfollow_actions",
)

LIST_CSV_FIELDS: tuple[str, ...] = (
    "original_posts",
    "liked_posts",
    "reposted_posts",
    "quoted_posts",
    "replied_posts",
    "cohort_followers",
    "cohort_followees",
    "follow_actions",
)


def null_unknowable() -> None:
    """Return the sentinel for fields the snapshot cannot observe."""
    return None


def empty_derived_stats_shell(
    did: str | None,
    handle: str | None,
    window_start: str,
    window_end: str,
) -> dict[str, Any]:
    """Build a derived-stats object with mandatory nulls and empty knowable lists.

    Parameters
    ----------
    did
        Member DID, or None when unresolved.
    handle
        Member handle, or None when unresolved.
    window_start, window_end
        ISO-8601 window bounds shared across the cohort.

    Returns
    -------
    dict[str, Any]
        Object with keys in ``DERIVED_STAT_KEYS`` order. ``saved_posts`` and
        ``unfollow_actions`` are None. Knowable list fields start as [].
    """
    shell: dict[str, Any] = {key: None for key in DERIVED_STAT_KEYS}
    shell["did"] = did
    shell["handle"] = handle
    shell["window_start"] = window_start
    shell["window_end"] = window_end
    for key in KNOWABLE_LIST_FIELDS:
        shell[key] = []
    shell["saved_posts"] = null_unknowable()
    shell["unfollow_actions"] = null_unknowable()
    return shell

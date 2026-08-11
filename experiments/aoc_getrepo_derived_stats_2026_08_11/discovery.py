"""Discover AOC and her most recent followers via the public AppView."""

from __future__ import annotations

from dataclasses import dataclass

from atproto import Client

from experiments.aoc_getrepo_derived_stats_2026_08_11.constants import (
    FOLLOWER_SAMPLE_SIZE,
    FOLLOWERS_PAGE_SIZE,
    PROFILES_BATCH_SIZE,
    TARGET_HANDLE,
)


@dataclass(frozen=True)
class CohortMember:
    """One account in the AOC-plus-followers cohort."""

    did: str
    handle: str
    followers_count: int | None
    display_name: str | None
    is_seed: bool


@dataclass(frozen=True)
class CohortResult:
    """Ordered cohort with the seed account first."""

    members: tuple[CohortMember, ...]
    target_did: str


def _batched(items: list[str], batch_size: int) -> list[list[str]]:
    return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]


def _member_from_detailed_profile(profile, is_seed: bool) -> CohortMember:
    return CohortMember(
        did=profile.did,
        handle=profile.handle,
        followers_count=getattr(profile, "followers_count", None),
        display_name=getattr(profile, "display_name", None),
        is_seed=is_seed,
    )


def _fetch_recent_followers(
    client: Client, target_did: str, limit: int
) -> list[tuple[str, str]]:
    """Return up to ``limit`` newest followers as (did, handle) pairs."""
    followers: list[tuple[str, str]] = []
    cursor = None
    while len(followers) < limit:
        params: dict = {"actor": target_did, "limit": FOLLOWERS_PAGE_SIZE}
        if cursor is not None:
            params["cursor"] = cursor
        response = client.app.bsky.graph.get_followers(params)
        if not response.followers:
            break
        for follower in response.followers:
            followers.append((follower.did, follower.handle))
            if len(followers) >= limit:
                break
        cursor = response.cursor
        if not cursor:
            break
    return followers


def _profiles_by_did(client: Client, dids: list[str]) -> dict:
    """Load detailed AppView profiles keyed by DID."""
    by_did: dict = {}
    for batch in _batched(dids, PROFILES_BATCH_SIZE):
        for profile in client.app.bsky.actor.get_profiles({"actors": batch}).profiles:
            by_did[profile.did] = profile
    return by_did


def discover_cohort(client: Client) -> CohortResult:
    """Resolve AOC and her most recent followers into a fixed-size cohort.

    Uses the public AppView only. Follower listing is newest-first. No
    min-follower or recent-post filters are applied.

    Parameters
    ----------
    client
        Public or authenticated AppView client.

    Returns
    -------
    CohortResult
        Seed account first, then up to ``FOLLOWER_SAMPLE_SIZE`` followers.
        Each member includes AppView ``followers_count`` when available.
    """
    seed_profile = client.app.bsky.actor.get_profile({"actor": TARGET_HANDLE})
    seed = _member_from_detailed_profile(seed_profile, is_seed=True)

    follower_pairs = _fetch_recent_followers(client, seed.did, FOLLOWER_SAMPLE_SIZE)
    follower_dids = [did for did, _ in follower_pairs]
    profiles = _profiles_by_did(client, follower_dids)

    followers: list[CohortMember] = []
    for did, handle in follower_pairs:
        profile = profiles.get(did)
        if profile is None:
            followers.append(
                CohortMember(
                    did=did,
                    handle=handle,
                    followers_count=None,
                    display_name=None,
                    is_seed=False,
                )
            )
            continue
        followers.append(_member_from_detailed_profile(profile, is_seed=False))

    return CohortResult(members=tuple([seed, *followers]), target_did=seed.did)

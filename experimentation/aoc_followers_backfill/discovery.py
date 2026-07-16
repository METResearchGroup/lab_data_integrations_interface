from datetime import UTC, datetime, timedelta

from atproto import Client

from experimentation.aoc_followers_backfill.constants import (
    AUTHOR_FEED_CHECK_LIMIT,
    FOLLOWERS_PAGE_SIZE,
    MAX_FOLLOWERS_TO_EVALUATE,
    MIN_FOLLOWERS,
    MIN_POSTS_LAST_7_DAYS,
    NUM_USERS_TARGET,
    PROFILES_BATCH_SIZE,
    TARGET_HANDLE,
)


def _batched(items: list, batch_size: int) -> list[list]:
    return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]


def _parse_bsky_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _count_posts_last_7_days(client: Client, did: str) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=7)
    response = client.app.bsky.feed.get_author_feed(
        {"actor": did, "limit": AUTHOR_FEED_CHECK_LIMIT}
    )
    count = 0
    for item in response.feed:
        created_at = getattr(item.post.record, "created_at", None)
        if created_at and _parse_bsky_datetime(created_at) >= cutoff:
            count += 1
    return count


def _qualify_profile(client: Client, profile) -> dict | None:
    """Returns a qualified-user dict if `profile` passes both filters, else None."""
    if (profile.followers_count or 0) <= MIN_FOLLOWERS:
        return None
    posts_last_7_days = _count_posts_last_7_days(client, profile.did)
    if posts_last_7_days < MIN_POSTS_LAST_7_DAYS:
        return None
    return {
        "handle": profile.handle,
        "did": profile.did,
        "followers_count": profile.followers_count,
        "posts_last_7_days": posts_last_7_days,
    }


def _evaluate_profile_batch(client: Client, dids: list[str], remaining: int) -> list[dict]:
    """Fetches profiles for `dids` and returns up to `remaining` qualifying users."""
    qualified: list[dict] = []
    profiles = client.app.bsky.actor.get_profiles({"actors": dids}).profiles
    for profile in profiles:
        if len(qualified) >= remaining:
            break
        user = _qualify_profile(client, profile)
        if user:
            qualified.append(user)
    return qualified


def get_ten_users(client: Client) -> tuple[list[dict], int, str]:
    """Finds up to NUM_USERS_TARGET Bluesky users who follow TARGET_HANDLE,
    have > MIN_FOLLOWERS followers, and posted >= MIN_POSTS_LAST_7_DAYS times
    in the past week. Stops as soon as NUM_USERS_TARGET is reached, or once
    MAX_FOLLOWERS_TO_EVALUATE followers have been checked without enough
    qualifying, or once her follower list is exhausted.

    Returns (qualified_users, total_followers_evaluated, target_did).
    """
    target_did = client.app.bsky.actor.get_profile({"actor": TARGET_HANDLE}).did

    qualified: list[dict] = []
    evaluated = 0
    cursor = None

    while len(qualified) < NUM_USERS_TARGET and evaluated < MAX_FOLLOWERS_TO_EVALUATE:
        followers_response = client.app.bsky.graph.get_followers(
            {"actor": target_did, "limit": FOLLOWERS_PAGE_SIZE, "cursor": cursor}
        )
        follower_dids = [f.did for f in followers_response.followers]
        if not follower_dids:
            break

        for batch in _batched(follower_dids, PROFILES_BATCH_SIZE):
            evaluated += len(batch)
            remaining = NUM_USERS_TARGET - len(qualified)
            qualified.extend(_evaluate_profile_batch(client, batch, remaining))
            if len(qualified) >= NUM_USERS_TARGET:
                break

        cursor = followers_response.cursor
        if not cursor:
            break

    return qualified, evaluated, target_did

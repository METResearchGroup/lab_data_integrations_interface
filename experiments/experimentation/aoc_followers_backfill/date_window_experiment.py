import time

from atproto import Client

from experimentation.aoc_followers_backfill.backfill import backfill_user
from experimentation.aoc_followers_backfill.client import create_public_client, create_relay_client
from experimentation.aoc_followers_backfill.discovery import get_follower_dids

NUM_USERS = 100
SIX_MONTHS_DAYS_BACK = 182


def _time_backfill(
    user: dict, relay_client: Client, days_back: int
) -> tuple[float, int, str | None]:
    start = time.perf_counter()
    rows_by_type, error = backfill_user(user, relay_client=relay_client, days_back=days_back)
    duration = time.perf_counter() - start
    row_count = sum(len(rows) for rows in rows_by_type.values())
    return duration, row_count, error


def main() -> None:
    client = create_public_client()
    users, _ = get_follower_dids(client, NUM_USERS)

    relay_client = create_relay_client()

    durations: list[float] = []

    for i, user in enumerate(users, start=1):
        duration, rows, error = _time_backfill(user, relay_client, SIX_MONTHS_DAYS_BACK)
        durations.append(duration)

        status = f"error: {error}" if error else f"{rows} rows"
        print(f"[{i}/{len(users)}] {user['handle']} - {duration:.3f}s ({status})")

    total = sum(durations)
    n = len(users)
    mean = total / n if n else 0.0

    print()
    print(f"6 months back - total: {total:.2f}s, mean/user: {mean:.3f}s, users: {n}")


if __name__ == "__main__":
    main()

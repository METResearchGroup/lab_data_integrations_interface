import json
import time
from datetime import UTC, datetime

from atproto import Client

from experiments.backfill_shape_2026_08_13.backfill import backfill_user
from experiments.backfill_shape_2026_08_13.client import create_public_client, create_relay_client
from experiments.backfill_shape_2026_08_13.constants import (
    BATCH_SIZE,
    PROFILES_BATCH_SIZE,
    USERS_FILE,
)
from experiments.backfill_shape_2026_08_13.landing_zone import BufferSet, create_run_dir


def load_handles() -> list[str]:
    with open(USERS_FILE, encoding="utf-8") as f:
        return json.load(f)["handles"]


def resolve_users(client: Client, handles: list[str]) -> list[dict]:
    """Resolves handles to DIDs. Handles that don't resolve are dropped with a
    warning rather than failing the run."""
    users: list[dict] = []
    for i in range(0, len(handles), PROFILES_BATCH_SIZE):
        batch = handles[i : i + PROFILES_BATCH_SIZE]
        profiles = client.app.bsky.actor.get_profiles({"actors": batch}).profiles
        users.extend({"handle": p.handle, "did": p.did} for p in profiles)

    resolved = {u["handle"] for u in users}
    for handle in handles:
        if handle not in resolved:
            print(f"warning: {handle} did not resolve, skipping")
    return users


def main() -> None:
    run_id = datetime.now(UTC).strftime("%Y_%m_%d-%H:%M:%S")
    run_dir = create_run_dir(run_id)

    users = resolve_users(create_public_client(), load_handles())
    relay_client = create_relay_client()
    buffers = BufferSet(run_id, run_dir)

    for i, user in enumerate(users, start=1):
        start = time.perf_counter()
        rows_by_type, error = backfill_user(user, relay_client)
        duration = time.perf_counter() - start

        status = error if error else f"{sum(len(r) for r in rows_by_type.values())} rows"
        print(f"[{i}/{len(users)}] {user['handle']} - {duration:.3f}s - {status}")

        buffers.add(user, rows_by_type, error)
        if i % BATCH_SIZE == 0:
            batch_dir = buffers.flush()
            print(f"  flushed {batch_dir}")

    # Trailing partial batch. No-ops when len(users) is an exact multiple.
    batch_dir = buffers.flush()
    if batch_dir:
        print(f"  flushed {batch_dir}")

    print(f"Wrote {buffers.batch_index} batches to {run_dir}")


if __name__ == "__main__":
    main()

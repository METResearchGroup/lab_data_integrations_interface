from datetime import UTC, datetime

from experimentation.aoc_followers_backfill.backfill import backfill_user
from experimentation.aoc_followers_backfill.client import create_client, create_relay_client
from experimentation.aoc_followers_backfill.constants import TARGET_COLLECTIONS
from experimentation.aoc_followers_backfill.discovery import get_ten_users
from experimentation.aoc_followers_backfill.output import write_outputs


def main() -> None:
    run_start = datetime.now(UTC)

    client = create_client()
    users, evaluated, target_did = get_ten_users(client)

    relay_client = create_relay_client()
    combined_rows: dict[str, list[dict]] = {name: [] for name in set(TARGET_COLLECTIONS.values())}
    errors: list[dict] = []

    for user in users:
        rows_by_type, error = backfill_user(user, relay_client=relay_client)
        if error:
            errors.append({"did": user["did"], "handle": user["handle"], "reason": error})
            continue
        for name, rows in rows_by_type.items():
            combined_rows[name].extend(rows)

    output_dir = write_outputs(
        target_did=target_did,
        users=users,
        users_evaluated=evaluated,
        rows_by_type=combined_rows,
        errors=errors,
        run_start=run_start,
    )
    print(f"Wrote output to {output_dir}")


if __name__ == "__main__":
    main()

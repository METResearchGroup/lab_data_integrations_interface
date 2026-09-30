import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

from experimentation.aoc_followers_backfill.constants import (
    DAYS_BACK,
    FOLLOW_CSV_FIELDNAMES,
    LIKE_REPOST_CSV_FIELDNAMES,
    MIN_FOLLOWERS,
    MIN_POSTS_LAST_7_DAYS,
    NUM_USERS_TARGET,
    POST_CSV_FIELDNAMES,
    TARGET_HANDLE,
)

OUTPUT_ROOT = Path(__file__).parent / "data"

_FIELDNAMES_BY_TYPE = {
    "posts": POST_CSV_FIELDNAMES,
    "likes": LIKE_REPOST_CSV_FIELDNAMES,
    "reposts": LIKE_REPOST_CSV_FIELDNAMES,
    "follows": FOLLOW_CSV_FIELDNAMES,
}


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_outputs(
    target_did: str,
    users: list[dict],
    users_evaluated: int,
    rows_by_type: dict[str, list[dict]],
    errors: list[dict],
    run_start: datetime,
) -> Path:
    timestamp = run_start.strftime("%Y_%m_%d-%H:%M:%S")
    output_dir = OUTPUT_ROOT / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    for type_name, fieldnames in _FIELDNAMES_BY_TYPE.items():
        _write_csv(output_dir / f"{type_name}.csv", rows_by_type[type_name], fieldnames)

    cutoff = run_start - timedelta(days=DAYS_BACK)
    metadata = {
        "run_timestamp": run_start.isoformat(),
        "target_account": {"handle": TARGET_HANDLE, "did": target_did},
        "selection_criteria": {
            "min_followers": MIN_FOLLOWERS,
            "min_posts_last_7_days": MIN_POSTS_LAST_7_DAYS,
        },
        "time_window": {"start": cutoff.isoformat(), "end": run_start.isoformat()},
        "users_requested": NUM_USERS_TARGET,
        "users_found": len(users),
        "followers_evaluated": users_evaluated,
        "users": users,
        "record_counts": {name: len(rows_by_type[name]) for name in _FIELDNAMES_BY_TYPE},
        "source_method": "com.atproto.sync.getRepo",
        "errors": errors,
    }
    with open(output_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    return output_dir

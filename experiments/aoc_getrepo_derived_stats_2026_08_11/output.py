"""Write timestamped raw dumps, derived stats, and run metadata."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from experiments.aoc_getrepo_derived_stats_2026_08_11.constants import (
    COHORT_SIZE_MAX,
    FOLLOW_CSV_FIELDNAMES,
    FOLLOWER_SAMPLE_SIZE,
    LIKE_REPOST_CSV_FIELDNAMES,
    POST_CSV_FIELDNAMES,
    TARGET_HANDLE,
)
from experiments.aoc_getrepo_derived_stats_2026_08_11.discovery import CohortMember
from experiments.aoc_getrepo_derived_stats_2026_08_11.fetch_repos import RepoBundle
from experiments.aoc_getrepo_derived_stats_2026_08_11.schemas import (
    LIST_CSV_FIELDS,
    SCALAR_CSV_FIELDS,
)

OUTPUT_ROOT = Path(__file__).parent / "data"

_FIELDNAMES_BY_RAW = {
    "posts": POST_CSV_FIELDNAMES,
    "likes": LIKE_REPOST_CSV_FIELDNAMES,
    "reposts": LIKE_REPOST_CSV_FIELDNAMES,
    "follows": FOLLOW_CSV_FIELDNAMES,
}


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _raw_rows_for_bundle(bundle: RepoBundle) -> dict[str, list[dict[str, Any]]]:
    base = {"author_handle": bundle.handle, "author_did": bundle.did}
    return {
        "posts": [{**base, **asdict(row)} for row in bundle.posts],
        "likes": [{**base, **asdict(row)} for row in bundle.likes],
        "reposts": [{**base, **asdict(row)} for row in bundle.reposts],
        "follows": [{**base, **asdict(row)} for row in bundle.follows],
    }


def _derived_stats_dataframe(derived_stats: list[dict[str, Any]]) -> pd.DataFrame:
    flat_rows: list[dict[str, Any]] = []
    for row in derived_stats:
        flat: dict[str, Any] = {}
        for key in SCALAR_CSV_FIELDS:
            value = row.get(key)
            flat[key] = pd.NA if value is None else value
        for key in LIST_CSV_FIELDS:
            value = row.get(key)
            flat[key] = json.dumps(value) if value is not None else pd.NA
        flat_rows.append(flat)
    columns = list(SCALAR_CSV_FIELDS) + list(LIST_CSV_FIELDS)
    return pd.DataFrame(flat_rows, columns=columns)


def write_outputs(
    members: tuple[CohortMember, ...] | list[CohortMember],
    bundles: list[RepoBundle],
    derived_stats: list[dict[str, Any]],
    run_start: datetime,
    window_start: datetime,
    window_end: datetime,
) -> Path:
    """Persist raw CSVs, derived stats, and metadata under a timestamped folder.

    Parameters
    ----------
    members
        Discovered cohort members.
    bundles
        Fetched repo bundles (may include per-DID errors).
    derived_stats
        Derived-stat objects aligned to the cohort.
    run_start, window_start, window_end
        Run clock and activity window bounds.

    Returns
    -------
    Path
        Output directory path.
    """
    timestamp = run_start.strftime("%Y_%m_%d-%H:%M:%S")
    output_dir = OUTPUT_ROOT / timestamp
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    combined: dict[str, list[dict[str, Any]]] = {name: [] for name in _FIELDNAMES_BY_RAW}
    for bundle in bundles:
        for name, rows in _raw_rows_for_bundle(bundle).items():
            combined[name].extend(rows)

    for name, fieldnames in _FIELDNAMES_BY_RAW.items():
        _write_csv(raw_dir / f"{name}.csv", combined[name], fieldnames)

    derived_path = output_dir / "derived_stats.json"
    derived_path.write_text(json.dumps(derived_stats, indent=2), encoding="utf-8")
    _derived_stats_dataframe(derived_stats).to_csv(
        output_dir / "derived_stats.csv", index=False
    )

    errors = [
        {"did": bundle.did, "handle": bundle.handle, "reason": bundle.error}
        for bundle in bundles
        if bundle.error
    ]
    metadata = {
        "run_timestamp": run_start.isoformat(),
        "target_account": {"handle": TARGET_HANDLE, "did": members[0].did if members else None},
        "users_requested_followers": FOLLOWER_SAMPLE_SIZE,
        "cohort_size_expected_max": COHORT_SIZE_MAX,
        "cohort_size_actual": len(members),
        "time_window": {
            "start": window_start.isoformat(),
            "end": window_end.isoformat(),
            "days_back": (window_end - window_start).days,
        },
        "users": [
            {
                "did": member.did,
                "handle": member.handle,
                "followers_count": member.followers_count,
                "is_seed": member.is_seed,
            }
            for member in members
        ],
        "record_counts": {name: len(rows) for name, rows in combined.items()},
        "errors": errors,
        "source_methods": {
            "discovery": "appview_discovery",
            "followers_count": "appview_followers_count",
            "repos": "relay_getRepo",
            "decode": "mst_decode_import",
        },
        "unavailable_fields": [
            "saved_posts",
            "unfollow_actions",
            "quoted_post_body",
            "parent_post_body",
        ],
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    return output_dir

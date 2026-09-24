import csv
import json
import statistics
from datetime import datetime
from pathlib import Path

from experimentation.aoc_followers_backfill.constants import TARGET_HANDLE, TIMING_SCALES

OUTPUT_ROOT = Path(__file__).parent / "data"

RAW_CSV_FIELDNAMES = [
    "call_index",
    "handle",
    "did",
    "duration_seconds",
    "repo_size_bytes",
    "error",
    "rate_limited",
]


def _percentile(values: list[float], pct: float) -> float:
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    index = min(int(len(ordered) * pct), len(ordered) - 1)
    return ordered[index]


def _tier_stats(calls: list[dict]) -> dict:
    durations = [c["duration_seconds"] for c in calls]
    successes = [c for c in calls if c["error"] is None]
    errors = [c for c in calls if c["error"] is not None]
    sizes = [c["repo_size_bytes"] for c in successes if c["repo_size_bytes"] is not None]

    return {
        "user_count": len(calls),
        "success_count": len(successes),
        "error_count": len(errors),
        "rate_limited_count": sum(1 for c in calls if c["rate_limited"]),
        "total_elapsed_seconds": sum(durations),
        "mean_seconds": statistics.mean(durations) if durations else None,
        "median_seconds": statistics.median(durations) if durations else None,
        "p95_seconds": _percentile(durations, 0.95) if durations else None,
        "min_seconds": min(durations) if durations else None,
        "max_seconds": max(durations) if durations else None,
        "mean_repo_size_bytes": statistics.mean(sizes) if sizes else None,
    }


def write_timing_outputs(
    target_did: str,
    calls: list[dict],
    run_start: datetime,
) -> Path:
    timestamp = run_start.strftime("%Y_%m_%d-%H:%M:%S")
    output_dir = OUTPUT_ROOT / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_dir / "timing_raw.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RAW_CSV_FIELDNAMES)
        writer.writeheader()
        for i, call in enumerate(calls, start=1):
            writer.writerow({"call_index": i, **call})

    tiers = {str(n): _tier_stats(calls[:n]) for n in sorted(TIMING_SCALES) if n <= len(calls)}

    metadata = {
        "run_timestamp": run_start.isoformat(),
        "target_account": {"handle": TARGET_HANDLE, "did": target_did},
        "scales": sorted(TIMING_SCALES),
        "measured": "com.atproto.sync.getRepo network call only (not decode, not discovery)",
        "tiers": tiers,
    }
    with open(output_dir / "timing_summary.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    return output_dir

"""One-time migration: flatten nested features/{timestamp}/*.csv to flat features/{feature}.csv.

Run from the repo root:

    PYTHONPATH=. uv run python scripts/flatten_bluesky_features.py \\
        --dataset-id bluesky_<uuid> --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from data_platform.generate_features.registry import FEATURE_REGISTRY
from data_platform.utils.dataset import dataset_root, validate_dataset_id
from data_platform.utils.storage import METADATA_FILENAME

DEFAULT_BATCH_SIZE = 64
DEFAULT_MAX_CONCURRENCY = 20
DEFAULT_MAX_LABEL_RETRIES = 3


def discover_nested_run_dirs(features_dir: Path) -> list[Path]:
    """List features/{timestamp}/ dirs sorted by name."""
    if not features_dir.exists():
        return []
    run_dirs = [
        path
        for path in features_dir.iterdir()
        if path.is_dir() and path.name != METADATA_FILENAME.replace(".json", "")
    ]
    return sorted(run_dirs, key=lambda path: path.name)


def load_run_metadata(run_dir: Path) -> dict:
    metadata_path = run_dir / METADATA_FILENAME
    if not metadata_path.exists():
        return {}
    with metadata_path.open(encoding="utf-8") as f:
        return json.load(f)


def _read_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        return []
    with csv_path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def collect_feature_rows(features_dir: Path, feature_name: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for run_dir in discover_nested_run_dirs(features_dir):
        csv_path = run_dir / f"{feature_name}.csv"
        for row in _read_csv_rows(csv_path):
            rows.append({**row, "label_timestamp": run_dir.name})
    return rows


def dedupe_rows_by_uri(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_uri: dict[str, dict[str, str]] = {}
    for row in rows:
        uri = row.get("uri", "")
        if not uri:
            continue
        existing = by_uri.get(uri)
        if existing is None or row.get("label_timestamp", "") > existing.get("label_timestamp", ""):
            by_uri[uri] = row
    return list(by_uri.values())


def _fieldnames_for_feature(feature_name: str, rows: list[dict[str, str]]) -> list[str]:
    if not rows:
        spec = FEATURE_REGISTRY[feature_name]
        model_fields = list(spec.model.model_fields.keys())
        if "label_timestamp" not in model_fields:
            return ["uri", "label_timestamp", *model_fields[1:]]
        return model_fields
    keys = set()
    for row in rows:
        keys.update(row.keys())
    ordered = ["uri", "label_timestamp"]
    for key in sorted(keys):
        if key not in ordered:
            ordered.append(key)
    return ordered


def write_flat_feature_csv(
    features_dir: Path,
    feature_name: str,
    rows: list[dict[str, str]],
) -> int:
    if not rows:
        return 0
    fieldnames = _fieldnames_for_feature(feature_name, rows)
    csv_path = features_dir / f"{feature_name}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def build_migrated_metadata(
    dataset_id: str,
    feature_counts: dict[str, int],
    source_preprocessed_run: str,
) -> dict:
    now = datetime.now(UTC).isoformat()
    features_meta = {
        name: {
            "status": "completed" if feature_counts.get(name, 0) > 0 else "pending",
            "labeled": feature_counts.get(name, 0),
            "failed_batches": 0,
        }
        for name in FEATURE_REGISTRY
    }
    all_completed = all(
        features_meta[name]["status"] == "completed" for name in FEATURE_REGISTRY
    )
    return {
        "dataset_id": dataset_id,
        "source_preprocessed_run": source_preprocessed_run,
        "sync_status": "completed" if all_completed else "in_progress",
        "features": features_meta,
        "config": {
            "batch_size": DEFAULT_BATCH_SIZE,
            "max_concurrency": DEFAULT_MAX_CONCURRENCY,
            "opik_enabled": False,
            "max_label_retries": DEFAULT_MAX_LABEL_RETRIES,
        },
        "migrated_from": "flatten_bluesky_features.py",
        "migrated_at": now,
        "updated_at": now,
    }


def delete_nested_run_dirs(run_dirs: list[Path]) -> None:
    for run_dir in run_dirs:
        shutil.rmtree(run_dir)


def flatten_features(dataset_id: str, *, dry_run: bool) -> None:
    dataset_id = validate_dataset_id(dataset_id)
    features_dir = dataset_root("bluesky", dataset_id) / "features"
    run_dirs = discover_nested_run_dirs(features_dir)
    if not run_dirs:
        print(f"flatten_features: no nested run dirs under {features_dir}")
        return

    latest_run = run_dirs[-1]
    latest_meta = load_run_metadata(latest_run)
    source_preprocessed_run = latest_meta.get("source_preprocessed_run", "")

    feature_counts: dict[str, int] = {}
    for feature_name in FEATURE_REGISTRY:
        rows = dedupe_rows_by_uri(collect_feature_rows(features_dir, feature_name))
        feature_counts[feature_name] = len(rows)
        print(
            f"  {feature_name}: {len(run_dirs)} run dirs, "
            f"{len(collect_feature_rows(features_dir, feature_name))} raw rows, "
            f"{len(rows)} deduped"
        )

    metadata = build_migrated_metadata(
        dataset_id,
        feature_counts,
        source_preprocessed_run,
    )

    if dry_run:
        print("flatten_features: dry-run — no writes")
        print(f"  would delete: {[p.name for p in run_dirs]}")
        print(json.dumps(metadata, indent=2))
        return

    print(
        "WARNING: This permanently deletes nested features/{timestamp}/ directories."
    )
    features_dir.mkdir(parents=True, exist_ok=True)
    for feature_name in FEATURE_REGISTRY:
        rows = dedupe_rows_by_uri(collect_feature_rows(features_dir, feature_name))
        write_flat_feature_csv(features_dir, feature_name, rows)

    metadata_path = features_dir / METADATA_FILENAME
    tmp_path = features_dir / f"{METADATA_FILENAME}.tmp"
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    tmp_path.replace(metadata_path)

    delete_nested_run_dirs(run_dirs)
    print(f"flatten_features: wrote flat CSVs and metadata to {features_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Flatten nested Bluesky feature runs.")
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    flatten_features(args.dataset_id, dry_run=args.dry_run)


if __name__ == "__main__":
    main()

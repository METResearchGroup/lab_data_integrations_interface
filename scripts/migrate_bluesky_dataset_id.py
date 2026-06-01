"""One-time migration: move legacy bluesky stage dirs under {dataset_id}/.

Run from repo root:

    PYTHONPATH=. uv run python scripts/migrate_bluesky_dataset_id.py --dry-run
    PYTHONPATH=. uv run python scripts/migrate_bluesky_dataset_id.py
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

import yaml

from data_platform.utils.dataset import (
    validate_dataset_id,
    write_dataset_manifest,
)

STAGES = ("raw", "preprocessed", "features", "curated")
SOURCE_KEYS = ("source_raw_run", "source_preprocessed_run")
CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "data_platform/ingestion/configs/bluesky/mirrorview.yaml"
)
_DATA_ROOT = Path(__file__).resolve().parents[1] / "data_platform" / "data"
BLUESKY_ROOT = _DATA_ROOT / "bluesky"


def _load_dataset_id_from_config(config_path: Path) -> str:
    with config_path.open(encoding="utf-8") as f:
        config = yaml.safe_load(f)
    dataset_id = config.get("dataset_id")
    if not dataset_id:
        raise ValueError(f"dataset_id missing from {config_path}")
    return validate_dataset_id(str(dataset_id))


def _normalize_lineage_path(value: str) -> str:
    if not value:
        return value
    path = Path(value)
    parts = path.parts
    for stage in STAGES:
        if stage in parts:
            idx = parts.index(stage)
            return str(Path(*parts[idx:]))
    return value.replace("\\", "/")


def _patch_metadata(metadata: dict[str, Any], dataset_id: str) -> dict[str, Any]:
    patched = dict(metadata)
    patched["dataset_id"] = dataset_id
    for key in SOURCE_KEYS:
        if key in patched and patched[key] is not None:
            patched[key] = _normalize_lineage_path(str(patched[key]))
    return patched


def _stage_run_counts(dataset_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for stage in STAGES:
        stage_dir = dataset_dir / stage
        if not stage_dir.exists():
            counts[stage] = 0
            continue
        counts[stage] = sum(1 for p in stage_dir.iterdir() if p.is_dir())
    return counts


def migrate(*, dry_run: bool, dataset_id: str, config_path: Path) -> None:
    dataset_id = validate_dataset_id(dataset_id)
    dataset_dir = BLUESKY_ROOT / dataset_id

    moves: list[tuple[Path, Path]] = []
    for stage in STAGES:
        src = BLUESKY_ROOT / stage
        if not src.exists():
            continue
        dst = dataset_dir / stage
        moves.append((src, dst))

    metadata_files = list(BLUESKY_ROOT.rglob("metadata.json"))
    # After move, metadata will be under dataset_dir; collect from stages pre-move
    stage_metadata = [
        p for p in metadata_files if p.parent.parent in {BLUESKY_ROOT / stage for stage in STAGES}
    ]

    print(f"dataset_id: {dataset_id}")
    print(f"target: {dataset_dir}")
    for src, dst in moves:
        print(f"  move {src} -> {dst}")
    print(f"  patch {len(stage_metadata)} metadata.json file(s)")
    if not dry_run:
        dataset_dir.mkdir(parents=True, exist_ok=True)
        for src, dst in moves:
            if dst.exists():
                raise FileExistsError(f"Refusing to overwrite existing path: {dst}")
            shutil.move(str(src), str(dst))

        manifest_path = write_dataset_manifest(
            "bluesky",
            dataset_id,
            name="mirrorview",
            ingestion_config=str(config_path.relative_to(Path(__file__).resolve().parents[1])),
        )
        print(f"  wrote {manifest_path}")

        for metadata_path in dataset_dir.rglob("metadata.json"):
            with metadata_path.open(encoding="utf-8") as f:
                metadata = json.load(f)
            patched = _patch_metadata(metadata, dataset_id)
            with metadata_path.open("w", encoding="utf-8") as f:
                json.dump(patched, f, indent=2)

    counts = (
        _stage_run_counts(dataset_dir)
        if not dry_run
        else {
            stage: sum(1 for p in (BLUESKY_ROOT / stage).iterdir() if p.is_dir())
            for stage in STAGES
            if (BLUESKY_ROOT / stage).exists()
        }
    )
    print("run counts:", counts)
    if dry_run:
        print("(dry-run: no changes written)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate Bluesky data under dataset_id")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned moves and patches without writing",
    )
    parser.add_argument(
        "--dataset-id",
        default=None,
        help="Override dataset_id (default: read from mirrorview.yaml)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=CONFIG_PATH,
        help="Ingestion config containing dataset_id",
    )
    args = parser.parse_args()
    dataset_id = args.dataset_id or _load_dataset_id_from_config(args.config)
    migrate(dry_run=args.dry_run, dataset_id=dataset_id, config_path=args.config)


if __name__ == "__main__":
    main()

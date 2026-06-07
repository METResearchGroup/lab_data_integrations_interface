from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"

DATASET_ID_PATTERN = re.compile(
    r"^(bluesky|reddit|twitter)_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
MANIFEST_FILENAME = "dataset.json"


def validate_dataset_id(dataset_id: str) -> str:
    if not DATASET_ID_PATTERN.match(dataset_id):
        raise ValueError(
            "dataset_id must match {platform}_{uuid} where platform is bluesky, reddit, or twitter "
            "(lowercase RFC 4122 hex with hyphens)"
        )
    return dataset_id


def dataset_root(platform: str, dataset_id: str) -> Path:
    validate_dataset_id(dataset_id)
    return _DATA_ROOT / platform / dataset_id


def relative_run_path(dataset_root_path: Path, run_dir: Path) -> str:
    return str(run_dir.relative_to(dataset_root_path))


def load_dataset_manifest(platform: str, dataset_id: str) -> dict[str, Any]:
    path = dataset_root(platform, dataset_id) / MANIFEST_FILENAME
    if not path.exists():
        raise FileNotFoundError(f"Dataset manifest not found: {path}")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_dataset_format(platform: str, dataset_id: str) -> Literal["csv", "parquet"]:
    """Read the output format from dataset.json, defaulting to csv for existing datasets."""
    try:
        manifest = load_dataset_manifest(platform, dataset_id)
    except FileNotFoundError:
        return "csv"
    fmt = manifest.get("format", "csv")
    if fmt not in ("csv", "parquet"):
        raise ValueError(f"Invalid format in dataset manifest: {fmt!r}")
    return fmt  # type: ignore[return-value]


def write_dataset_manifest(
    platform: str,
    dataset_id: str,
    *,
    name: str,
    ingestion_config: str,
    format: Literal["csv", "parquet"] = "csv",
    created_at: str | None = None,
) -> Path:
    root = dataset_root(platform, dataset_id)
    root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "dataset_id": validate_dataset_id(dataset_id),
        "platform": platform,
        "name": name,
        "created_at": created_at or datetime.now(UTC).isoformat(),
        "ingestion_config": ingestion_config,
        "format": format,
    }
    path = root / MANIFEST_FILENAME
    with path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return path

"""Append exhausted atomic-batch failures to features/deadletter.jsonl."""

from __future__ import annotations

import json
from pathlib import Path

from lib.timestamp_utils import get_current_timestamp


def deadletter_path(features_dir: Path) -> Path:
    """Return the path to features/deadletter.jsonl for a dataset."""
    return features_dir / "deadletter.jsonl"


def append_deadletter_batch(
    features_dir: Path,
    *,
    feature: str,
    uris: list[str],
    error: str,
    attempts: int,
    batch_index: int,
) -> None:
    """Append one JSON line describing a batch that failed after all retries."""
    features_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "feature": feature,
        "uris": uris,
        "error": error,
        "attempts": attempts,
        "ts": get_current_timestamp(),
        "batch_index": batch_index,
    }
    path = deadletter_path(features_dir)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

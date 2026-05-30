from __future__ import annotations

from pathlib import Path


def feature_glob(features_root: Path, feature_name: str) -> str:
    """Return a POSIX glob for feature CSVs across all feature run directories."""
    return (features_root / "*" / f"{feature_name}.csv").as_posix()

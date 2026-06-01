from __future__ import annotations

from pathlib import Path


def feature_csv_path(features_root: Path, feature_name: str) -> Path:
    """Return the feature label CSV path under the features root."""
    return features_root / f"{feature_name}.csv"


def feature_glob(features_root: Path, feature_name: str) -> str:
    """Return a POSIX path string for DuckDB read_csv on the feature CSV."""
    return feature_csv_path(features_root, feature_name).as_posix()

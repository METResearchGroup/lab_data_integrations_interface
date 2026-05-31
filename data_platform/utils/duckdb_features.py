from __future__ import annotations

from pathlib import Path


def flat_feature_csv(features_root: Path, feature_name: str) -> Path:
    """Return the flat feature CSV path at features root."""
    return features_root / f"{feature_name}.csv"


def feature_glob(features_root: Path, feature_name: str) -> str:
    """Return a POSIX path for the flat feature CSV (breaking: no nested glob)."""
    return flat_feature_csv(features_root, feature_name).as_posix()

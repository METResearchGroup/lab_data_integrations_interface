from __future__ import annotations

from pathlib import Path

import pandas as pd

from data_platform.utils.feature_labels import FeatureLabelQuery


def test_labeled_ids_from_feature_glob(tmp_path: Path) -> None:
    features_root = tmp_path / "features"
    run_dir = features_root / "2026_01_01-00:00:00"
    run_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {"uri": "at://a/post/1", "is_political": True},
            {"uri": "at://b/post/2", "is_political": False},
        ]
    ).to_csv(run_dir / "is_political.csv", index=False)

    query = FeatureLabelQuery(features_root=features_root)
    labeled = query.labeled_ids("is_political")
    assert labeled == {"at://a/post/1", "at://b/post/2"}

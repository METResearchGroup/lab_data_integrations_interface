from __future__ import annotations

from pathlib import Path

import pandas as pd

from data_platform.utils.feature_labels import FeatureLabelQuery


def test_labeled_ids_from_flat_feature_csv(tmp_path: Path) -> None:
    features_root = tmp_path / "features"
    features_root.mkdir(parents=True)
    pd.DataFrame(
        [
            {"uri": "at://a/post/1", "label_timestamp": "2026_01_01-00:00:00", "is_political": True},
            {"uri": "at://b/post/2", "label_timestamp": "2026_01_01-00:00:00", "is_political": False},
        ]
    ).to_csv(features_root / "is_political.csv", index=False)

    query = FeatureLabelQuery(features_root=features_root)
    labeled = query.labeled_ids("is_political")
    assert labeled == {"at://a/post/1", "at://b/post/2"}


def test_filter_unlabeled_excludes_labeled_uris(tmp_path: Path) -> None:
    features_root = tmp_path / "features"
    features_root.mkdir(parents=True)
    pd.DataFrame(
        [{"uri": "at://a/post/1", "label_timestamp": "2026_01_01-00:00:00", "is_political": True}]
    ).to_csv(features_root / "is_political.csv", index=False)

    records = pd.DataFrame(
        [
            {"uri": "at://a/post/1", "text": "one"},
            {"uri": "at://b/post/2", "text": "two"},
        ]
    )
    query = FeatureLabelQuery(features_root=features_root)
    pending = query.filter_unlabeled(records, "is_political")
    assert len(pending) == 1
    assert pending.iloc[0]["uri"] == "at://b/post/2"

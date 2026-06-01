from __future__ import annotations

import pandas as pd

from data_platform.utils.feature_labels import FeatureLabelQuery
from tests.data_platform.conftest import make_political_feature_rows, write_feature_csv
from tests.data_platform.constants import LABEL_TIMESTAMP, URI_POST_A, URI_POST_B


def test_labeled_ids_from_feature_csv(tmp_path) -> None:
    features_root = tmp_path / "features"
    write_feature_csv(features_root, "is_political", make_political_feature_rows())

    query = FeatureLabelQuery(features_root=features_root)
    labeled = query.labeled_ids("is_political")
    assert labeled == {URI_POST_A, URI_POST_B}


def test_filter_unlabeled_excludes_labeled_uris(tmp_path) -> None:
    features_root = tmp_path / "features"
    write_feature_csv(
        features_root,
        "is_political",
        [{"uri": URI_POST_A, "label_timestamp": LABEL_TIMESTAMP, "is_political": True}],
    )

    records = pd.DataFrame(
        [
            {"uri": URI_POST_A, "text": "one"},
            {"uri": URI_POST_B, "text": "two"},
        ]
    )
    query = FeatureLabelQuery(features_root=features_root)
    pending = query.filter_unlabeled(records, "is_political")
    assert len(pending) == 1
    assert pending.iloc[0]["uri"] == URI_POST_B

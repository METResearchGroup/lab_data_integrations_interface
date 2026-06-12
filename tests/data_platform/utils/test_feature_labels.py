from __future__ import annotations

import pandas as pd
from pydantic import BaseModel

from data_platform.utils.feature_labels import FeatureLabelQuery
from data_platform.utils.storage import StorageManager
from tests.data_platform.conftest import make_political_feature_rows, write_feature_csv
from tests.data_platform.constants import (
    FEATURES_DATASET_ID,
    LABEL_TIMESTAMP,
    URI_POST_A,
    URI_POST_B,
)


def test_labeled_ids_from_feature_csv(data_root) -> None:
    feature_storage = StorageManager(
        "bluesky", "features", BaseModel, FEATURES_DATASET_ID, records_filename="features"
    )
    write_feature_csv(feature_storage.root_dir, "is_political", make_political_feature_rows())

    query = FeatureLabelQuery(feature_storage=feature_storage)
    labeled = query.labeled_ids("is_political")
    assert labeled == {URI_POST_A, URI_POST_B}


def test_filter_unlabeled_excludes_labeled_uris(data_root) -> None:
    feature_storage = StorageManager(
        "bluesky", "features", BaseModel, FEATURES_DATASET_ID, records_filename="features"
    )
    write_feature_csv(
        feature_storage.root_dir,
        "is_political",
        [{"uri": URI_POST_A, "label_timestamp": LABEL_TIMESTAMP, "is_political": True}],
    )

    records = pd.DataFrame(
        [
            {"uri": URI_POST_A, "text": "one"},
            {"uri": URI_POST_B, "text": "two"},
        ]
    )
    query = FeatureLabelQuery(feature_storage=feature_storage)
    pending = query.filter_unlabeled(records, "is_political")
    assert len(pending) == 1
    assert pending.iloc[0]["uri"] == URI_POST_B

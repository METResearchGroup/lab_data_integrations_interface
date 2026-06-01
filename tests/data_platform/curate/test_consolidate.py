from __future__ import annotations

from pathlib import Path

import pandas as pd

from data_platform.curate.consolidate import ConsolidateConfig, build_wide_table
from tests.data_platform.conftest import (
    make_political_feature_rows,
    write_feature_csv,
    write_posts_csv,
)
from tests.data_platform.constants import LABEL_TIMESTAMP, URI_POST_A, URI_POST_B


def test_build_wide_table_joins_features(tmp_path: Path) -> None:
    posts_csv = tmp_path / "posts.csv"
    write_posts_csv(posts_csv)

    features_root = tmp_path / "features"
    write_feature_csv(features_root, "is_political", make_political_feature_rows())
    write_feature_csv(
        features_root,
        "is_news_or_opinion",
        [
            {"uri": URI_POST_A, "label_timestamp": LABEL_TIMESTAMP, "category": "news"},
            {"uri": URI_POST_B, "label_timestamp": LABEL_TIMESTAMP, "category": "opinion"},
        ],
    )

    wide = build_wide_table(
        ConsolidateConfig(
            posts_csv=posts_csv,
            features_root=features_root,
            feature_names=("is_political", "is_news_or_opinion"),
        )
    )

    assert len(wide) == 2
    assert "news_or_opinion_category" in wide.columns
    assert wide.loc[wide["uri"] == URI_POST_A, "news_or_opinion_category"].iloc[0] == "news"
    assert wide.loc[wide["uri"] == URI_POST_A, "is_political"].iloc[0] in {
        True,
        "True",
    }


def test_build_wide_table_supports_reddit_id_column_mapping(tmp_path: Path) -> None:
    comments_csv = tmp_path / "comments.csv"
    pd.DataFrame([{"comment_fullname": "t1_a", "body": "comment one"}]).to_csv(
        comments_csv,
        index=False,
    )

    features_root = tmp_path / "features"
    write_feature_csv(
        features_root,
        "is_political",
        [{"uri": "t1_a", "label_timestamp": LABEL_TIMESTAMP, "is_political": True}],
    )

    wide = build_wide_table(
        ConsolidateConfig(
            posts_csv=comments_csv,
            features_root=features_root,
            feature_names=("is_political",),
            id_column="comment_fullname",
            feature_csv_id_column="uri",
        )
    )

    assert len(wide) == 1
    assert wide.iloc[0]["comment_fullname"] == "t1_a"
    assert wide.iloc[0]["body"] == "comment one"
    assert wide.iloc[0]["is_political"] in {True, "True"}

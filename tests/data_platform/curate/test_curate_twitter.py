from __future__ import annotations

from pathlib import Path

import pandas as pd

from data_platform.curate.consolidate import ConsolidateConfig, build_wide_table
from data_platform.curate.curate_twitter import (
    FEATURE_FILE_ID_COLUMN,
    ID_COLUMN,
    curate,
)
from data_platform.utils.storage import TwitterStorageManager
from tests.data_platform.constants import LABEL_TIMESTAMP, VALID_TWITTER_DATASET_ID
from tests.data_platform.ingestion.twitter_conftest import mock_tweet_row


def _write_twitter_feature_csv(
    features_root: Path,
    feature_name: str,
    rows: list[dict[str, object]],
) -> None:
    features_root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(features_root / f"{feature_name}.csv", index=False)


def test_build_wide_table_joins_twitter_posts_on_tweet_id(tmp_path: Path) -> None:
    posts_file = tmp_path / "posts.csv"
    post_a = mock_tweet_row("1000000000000000001")
    post_b = mock_tweet_row("1000000000000000002")
    pd.DataFrame([post_a, post_b]).to_csv(posts_file, index=False)

    features_root = tmp_path / "features"
    _write_twitter_feature_csv(
        features_root,
        "is_political",
        [
            {
                FEATURE_FILE_ID_COLUMN: post_a["tweet_id"],
                "label_timestamp": LABEL_TIMESTAMP,
                "is_political": True,
            },
            {
                FEATURE_FILE_ID_COLUMN: post_b["tweet_id"],
                "label_timestamp": LABEL_TIMESTAMP,
                "is_political": False,
            },
        ],
    )
    _write_twitter_feature_csv(
        features_root,
        "is_news_or_opinion",
        [
            {
                FEATURE_FILE_ID_COLUMN: post_a["tweet_id"],
                "label_timestamp": LABEL_TIMESTAMP,
                "category": "opinion",
            },
            {
                FEATURE_FILE_ID_COLUMN: post_b["tweet_id"],
                "label_timestamp": LABEL_TIMESTAMP,
                "category": "news",
            },
        ],
    )
    _write_twitter_feature_csv(
        features_root,
        "is_likely_spam",
        [
            {
                FEATURE_FILE_ID_COLUMN: post_a["tweet_id"],
                "label_timestamp": LABEL_TIMESTAMP,
                "is_likely_spam": False,
            },
            {
                FEATURE_FILE_ID_COLUMN: post_b["tweet_id"],
                "label_timestamp": LABEL_TIMESTAMP,
                "is_likely_spam": True,
            },
        ],
    )

    wide = build_wide_table(
        ConsolidateConfig(
            posts_file=posts_file,
            features_root=features_root,
            feature_names=("is_political", "is_news_or_opinion"),
            id_column=ID_COLUMN,
            feature_file_id_column=FEATURE_FILE_ID_COLUMN,
        )
    )

    assert len(wide) == 2
    assert "text" in wide.columns
    assert "news_or_opinion_category" in wide.columns
    assert wide.loc[wide[ID_COLUMN] == post_a["tweet_id"], "is_political"].iloc[0] in {
        True,
        "True",
    }


def test_curate_writes_export_and_metadata(data_root) -> None:
    dataset_id = VALID_TWITTER_DATASET_ID
    root = data_root / "twitter" / dataset_id
    preprocessed_dir = root / "preprocessed" / "2026_06_01-00:00:00"
    preprocessed_dir.mkdir(parents=True)

    post_keep = mock_tweet_row("1000000000000000001")
    post_drop = mock_tweet_row("1000000000000000002")
    post_neutral = mock_tweet_row("1000000000000000003")
    pd.DataFrame([post_keep, post_drop, post_neutral]).to_csv(
        preprocessed_dir / "posts.csv", index=False
    )

    features_root = root / "features"
    features_root.mkdir(parents=True)
    for post, political, category, self_contained, structurally_complete, stance in [
        (post_keep, True, "opinion", True, True, "left"),
        (post_drop, True, "news", True, True, "left"),
        (post_neutral, True, "opinion", True, True, "neutral"),
    ]:
        feature_payloads = [
            (
                "is_political",
                {
                    FEATURE_FILE_ID_COLUMN: post["tweet_id"],
                    "label_timestamp": LABEL_TIMESTAMP,
                    "is_political": political,
                },
            ),
            (
                "is_news_or_opinion",
                {
                    FEATURE_FILE_ID_COLUMN: post["tweet_id"],
                    "label_timestamp": LABEL_TIMESTAMP,
                    "category": category,
                },
            ),
            (
                "is_likely_spam",
                {
                    FEATURE_FILE_ID_COLUMN: post["tweet_id"],
                    "label_timestamp": LABEL_TIMESTAMP,
                    "is_likely_spam": post is post_drop,
                },
            ),
            (
                "is_self_contained",
                {
                    FEATURE_FILE_ID_COLUMN: post["tweet_id"],
                    "label_timestamp": LABEL_TIMESTAMP,
                    "is_self_contained": self_contained,
                },
            ),
            (
                "is_structurally_complete",
                {
                    FEATURE_FILE_ID_COLUMN: post["tweet_id"],
                    "label_timestamp": LABEL_TIMESTAMP,
                    "is_structurally_complete": structurally_complete,
                },
            ),
            (
                "is_toxic_tiered",
                {
                    FEATURE_FILE_ID_COLUMN: post["tweet_id"],
                    "label_timestamp": LABEL_TIMESTAMP,
                    "toxicity_prob": 0.1,
                    "toxicity_tier": "low",
                },
            ),
            (
                "political_stance",
                {
                    FEATURE_FILE_ID_COLUMN: post["tweet_id"],
                    "label_timestamp": LABEL_TIMESTAMP,
                    "political_stance": stance,
                },
            ),
        ]
        for feature_name, payload in feature_payloads:
            path = features_root / f"{feature_name}.csv"
            rows = []
            if path.exists():
                rows = pd.read_csv(path, keep_default_na=False).to_dict(orient="records")
            rows.append(payload)
            pd.DataFrame(rows).to_csv(path, index=False)

    config_path = (
        Path(__file__).resolve().parents[3] / "data_platform/curate/configs/twitter/mirrorview.yaml"
    )
    output_path = curate(config_path, dataset_id)

    curated_storage = TwitterStorageManager("curated", dataset_id)
    run_dir = output_path.parent
    metadata = curated_storage.load_run_metadata(run_dir)
    curated = pd.read_csv(output_path, keep_default_na=False)

    assert output_path.name == "mirrorview.csv"
    assert len(curated) == 1
    assert str(curated.iloc[0][ID_COLUMN]) == post_keep["tweet_id"]
    assert "text" in curated.columns
    assert metadata["row_counts"]["after_filters"] == 1
    assert len(metadata["filter_results"]) == 6
    stance_step = next(
        step for step in metadata["filter_results"] if step["column"] == "political_stance"
    )
    assert stance_step["op"] == "in"
    assert stance_step["value"] == ["left", "right"]
    assert (
        metadata["filter_results"][0]["records_before"]
        >= metadata["filter_results"][-1]["records_passing"]
    )

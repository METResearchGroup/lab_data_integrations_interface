from __future__ import annotations

from pathlib import Path

import pandas as pd

from data_platform.curate.apply_rules import apply_rules, load_rules_config
from data_platform.curate.consolidate import ConsolidateConfig, build_wide_table
from data_platform.curate.curate_reddit import (
    FEATURE_CSV_ID_COLUMN,
    ID_COLUMN,
    curate_mirrorview,
)
from data_platform.utils.storage import RedditStorageManager
from tests.data_platform.constants import LABEL_TIMESTAMP, VALID_REDDIT_DATASET_ID
from tests.data_platform.ingestion.reddit_conftest import mock_comment_row


def _write_reddit_feature_csv(
    features_root: Path,
    feature_name: str,
    rows: list[dict[str, object]],
) -> None:
    features_root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(features_root / f"{feature_name}.csv", index=False)


def test_build_wide_table_joins_reddit_comments_on_comment_fullname(tmp_path: Path) -> None:
    comments_csv = tmp_path / "comments.csv"
    comment_a = mock_comment_row("t1_comment_a", subreddit="politics")
    comment_b = mock_comment_row("t1_comment_b", subreddit="politics")
    pd.DataFrame([comment_a, comment_b]).to_csv(comments_csv, index=False)

    features_root = tmp_path / "features"
    _write_reddit_feature_csv(
        features_root,
        "is_political",
        [
            {
                FEATURE_CSV_ID_COLUMN: comment_a["comment_fullname"],
                "label_timestamp": LABEL_TIMESTAMP,
                "is_political": True,
            },
            {
                FEATURE_CSV_ID_COLUMN: comment_b["comment_fullname"],
                "label_timestamp": LABEL_TIMESTAMP,
                "is_political": False,
            },
        ],
    )
    _write_reddit_feature_csv(
        features_root,
        "is_news_or_opinion",
        [
            {
                FEATURE_CSV_ID_COLUMN: comment_a["comment_fullname"],
                "label_timestamp": LABEL_TIMESTAMP,
                "category": "opinion",
            },
            {
                FEATURE_CSV_ID_COLUMN: comment_b["comment_fullname"],
                "label_timestamp": LABEL_TIMESTAMP,
                "category": "news",
            },
        ],
    )

    wide = build_wide_table(
        ConsolidateConfig(
            posts_csv=comments_csv,
            features_root=features_root,
            feature_names=("is_political", "is_news_or_opinion"),
            id_column=ID_COLUMN,
            feature_csv_id_column=FEATURE_CSV_ID_COLUMN,
        )
    )

    assert len(wide) == 2
    assert "body" in wide.columns
    assert "news_or_opinion_category" in wide.columns
    assert wide.loc[wide[ID_COLUMN] == comment_a["comment_fullname"], "is_political"].iloc[0] in {
        True,
        "True",
    }


def test_curate_mirrorview_writes_export_and_metadata(data_root) -> None:
    dataset_id = VALID_REDDIT_DATASET_ID
    root = data_root / "reddit" / dataset_id
    preprocessed_dir = root / "preprocessed" / "2026_06_01-00:00:00"
    preprocessed_dir.mkdir(parents=True)

    comment_keep = mock_comment_row("t1_keep", subreddit="politics")
    comment_drop = mock_comment_row("t1_drop", subreddit="politics")
    comment_neutral = mock_comment_row("t1_neutral", subreddit="politics")
    pd.DataFrame([comment_keep, comment_drop, comment_neutral]).to_csv(
        preprocessed_dir / "comments.csv", index=False
    )

    features_root = root / "features"
    features_root.mkdir(parents=True)
    for comment, political, category, self_contained, structurally_complete, stance in [
        (comment_keep, True, "opinion", True, True, "left"),
        (comment_drop, True, "news", True, True, "left"),
        (comment_neutral, True, "opinion", True, True, "neutral"),
    ]:
        feature_payloads = [
            (
                "is_political",
                {
                    FEATURE_CSV_ID_COLUMN: comment["comment_fullname"],
                    "label_timestamp": LABEL_TIMESTAMP,
                    "is_political": political,
                },
            ),
            (
                "is_news_or_opinion",
                {
                    FEATURE_CSV_ID_COLUMN: comment["comment_fullname"],
                    "label_timestamp": LABEL_TIMESTAMP,
                    "category": category,
                },
            ),
            (
                "is_self_contained",
                {
                    FEATURE_CSV_ID_COLUMN: comment["comment_fullname"],
                    "label_timestamp": LABEL_TIMESTAMP,
                    "is_self_contained": self_contained,
                },
            ),
            (
                "is_structurally_complete",
                {
                    FEATURE_CSV_ID_COLUMN: comment["comment_fullname"],
                    "label_timestamp": LABEL_TIMESTAMP,
                    "is_structurally_complete": structurally_complete,
                },
            ),
            (
                "is_toxic_tiered",
                {
                    FEATURE_CSV_ID_COLUMN: comment["comment_fullname"],
                    "label_timestamp": LABEL_TIMESTAMP,
                    "toxicity_prob": 0.1,
                    "toxicity_tier": "low",
                },
            ),
            (
                "political_stance",
                {
                    FEATURE_CSV_ID_COLUMN: comment["comment_fullname"],
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
        Path(__file__).resolve().parents[3]
        / "data_platform/curate/configs/reddit/mirrorview.yaml"
    )
    output_path = curate_mirrorview(config_path, dataset_id)

    curated_storage = RedditStorageManager("curated", dataset_id)
    run_dir = output_path.parent
    metadata = curated_storage.load_run_metadata(run_dir)
    curated = pd.read_csv(output_path, keep_default_na=False)

    assert output_path.name == "mirrorview.csv"
    assert len(curated) == 1
    assert curated.iloc[0][ID_COLUMN] == comment_keep["comment_fullname"]
    assert "body" in curated.columns
    assert metadata["row_counts"]["after_filters"] == 1
    assert len(metadata["filter_results"]) == 5
    assert metadata["filter_results"][0]["records_before"] >= metadata["filter_results"][-1][
        "records_passing"
    ]

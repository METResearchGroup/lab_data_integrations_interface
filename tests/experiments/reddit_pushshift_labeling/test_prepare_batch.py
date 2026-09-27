from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pytest

from data_platform.models.sync import SyncRedditCommentModel
from experiments.reddit_data_dump_labeling_2026_06_16.prepare_batch import (
    COMMENT_FIELDS,
    PROB_TOXIC_COLUMN,
    prepare_batch,
)
from experiments.reddit_data_dump_labeling_2026_06_16.seed_toxicity_features import (
    FEATURE_FIELDS,
    seed_toxicity_features,
)
from data_platform.generate_features.is_toxic_tiered.generate_feature import toxicity_tier_from_prob


def _sample_comment_row(*, comment_fullname: str = "t1_abc123", prob_toxic: float = 0.85) -> dict:
    return {
        "post_reddit_id": "1kbpq3k",
        "post_reddit_fullname": "t3_1kbpq3k",
        "subreddit": "politics",
        "comment_id": "abc123",
        "comment_fullname": comment_fullname,
        "parent_id": "t3_1kbpq3k",
        "author": "example_user",
        "body": "Example comment body",
        "score": 1,
        "created_utc": "2025-04-30 19:00:14-05:00",
        "permalink": "/r/politics/comments/1kbpq3k/example/abc123/",
        "depth": 0,
        "comment_rank": 0,
        "sync_timestamp": "2026_06_16-07:37:01",
        PROB_TOXIC_COLUMN: prob_toxic,
    }


def _write_batches_yaml(experiment_root: Path) -> None:
    (experiment_root / "batches.yaml").write_text(
        "\n".join(
            [
                "RC_2025-05:",
                "  dataset_id: reddit_c3e4a5b6-7d8e-9012-3456-789012345601",
                "  parquet: RC_2025-05/high_toxic_comments.parquet",
            ]
        ),
        encoding="utf-8",
    )


@pytest.fixture
def experiment_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    experiment_root = tmp_path / "experiment"
    batch_dir = experiment_root / "RC_2025-05"
    batch_dir.mkdir(parents=True)
    data_root = experiment_root / "data"
    data_root.mkdir()

    rows = [
        _sample_comment_row(comment_fullname="t1_row1"),
        _sample_comment_row(comment_fullname="t1_row2", prob_toxic=0.91),
    ]
    pd.DataFrame(rows).to_parquet(batch_dir / "high_toxic_comments.parquet", index=False)
    _write_batches_yaml(experiment_root)

    import experiments.reddit_data_dump_labeling_2026_06_16.paths as paths

    monkeypatch.setattr(paths, "EXPERIMENT_ROOT", experiment_root)
    monkeypatch.setattr(paths, "EXPERIMENT_DATA_ROOT", data_root)
    monkeypatch.setattr(paths, "BATCHES_PATH", experiment_root / "batches.yaml")
    return experiment_root


def test_prepare_batch_writes_valid_comments_csv(experiment_layout: Path) -> None:
    output_path = prepare_batch("RC_2025-05", experiment_root=experiment_layout)
    assert output_path.exists()

    with output_path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 2
    assert set(rows[0].keys()) == set(COMMENT_FIELDS)
    assert PROB_TOXIC_COLUMN not in rows[0]
    SyncRedditCommentModel.model_validate(rows[0])


def test_seed_toxicity_maps_prob_to_tier() -> None:
    assert toxicity_tier_from_prob(0.05) == "low"
    assert toxicity_tier_from_prob(0.5) == "medium"
    assert toxicity_tier_from_prob(0.9) == "high"


def test_seed_toxicity_writes_feature_csv(experiment_layout: Path) -> None:
    output_path = seed_toxicity_features("RC_2025-05", experiment_root=experiment_layout)
    assert output_path.exists()

    with output_path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 2
    assert set(rows[0].keys()) == set(FEATURE_FIELDS)
    assert rows[0]["uri"] == "t1_row1"
    assert rows[0]["toxicity_tier"] == "high"

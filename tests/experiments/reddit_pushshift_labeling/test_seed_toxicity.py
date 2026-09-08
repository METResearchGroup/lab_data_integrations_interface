from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pytest

from experiments.reddit_data_dump_labeling_2026_06_16.seed_toxicity_features import (
    FEATURE_FIELDS,
    PROB_TOXIC_COLUMN,
    seed_toxicity_features,
    toxicity_tier_from_prob,
)


def _sample_row(*, comment_fullname: str, prob_toxic: float) -> dict:
    return {
        "post_reddit_id": "1kbpq3k",
        "post_reddit_fullname": "t3_1kbpq3k",
        "subreddit": "politics",
        "comment_id": comment_fullname.removeprefix("t1_"),
        "comment_fullname": comment_fullname,
        "parent_id": "t3_1kbpq3k",
        "author": "example_user",
        "body": "Example comment body",
        "score": 1,
        "created_utc": "2025-04-30 19:00:14-05:00",
        "permalink": "/r/politics/comments/1kbpq3k/example/",
        "depth": 0,
        "comment_rank": 0,
        "sync_timestamp": "2026_06_16-07:37:01",
        PROB_TOXIC_COLUMN: prob_toxic,
    }


@pytest.fixture
def experiment_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    experiment_root = tmp_path / "experiment"
    batch_dir = experiment_root / "RC_2025-05"
    batch_dir.mkdir(parents=True)
    data_root = experiment_root / "data"
    data_root.mkdir()

    rows = [
        _sample_row(comment_fullname="t1_low", prob_toxic=0.05),
        _sample_row(comment_fullname="t1_medium", prob_toxic=0.5),
        _sample_row(comment_fullname="t1_high", prob_toxic=0.9),
    ]
    pd.DataFrame(rows).to_parquet(batch_dir / "high_toxic_comments.parquet", index=False)
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

    import experiments.reddit_data_dump_labeling_2026_06_16.paths as paths

    monkeypatch.setattr(paths, "EXPERIMENT_ROOT", experiment_root)
    monkeypatch.setattr(paths, "EXPERIMENT_DATA_ROOT", data_root)
    monkeypatch.setattr(paths, "BATCHES_PATH", experiment_root / "batches.yaml")
    return experiment_root


def test_toxicity_tier_thresholds() -> None:
    assert toxicity_tier_from_prob(0.05) == "low"
    assert toxicity_tier_from_prob(0.5) == "medium"
    assert toxicity_tier_from_prob(0.9) == "high"


def test_seed_toxicity_feature_schema(experiment_layout: Path) -> None:
    output_path = seed_toxicity_features("RC_2025-05", experiment_root=experiment_layout)
    with output_path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    tiers = {row["uri"]: row["toxicity_tier"] for row in rows}
    assert tiers["t1_low"] == "low"
    assert tiers["t1_medium"] == "medium"
    assert tiers["t1_high"] == "high"
    assert set(rows[0].keys()) == set(FEATURE_FIELDS)

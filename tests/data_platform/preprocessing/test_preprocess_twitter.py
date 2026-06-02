from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from data_platform.preprocessing import preprocess_twitter
from data_platform.preprocessing.validators import twitter_validators
from data_platform.utils.storage import TwitterStorageManager
from tests.data_platform.constants import VALID_TWITTER_DATASET_ID
from tests.data_platform.ingestion.twitter_conftest import mock_tweet_row


def _valid_text() -> str:
    return "This is a valid English tweet for preprocessing tests without external URLs."


def _tweet_row(**overrides: Any) -> dict[str, Any]:
    tweet_id = overrides.pop("tweet_id", "1000000000000000001")
    row = mock_tweet_row(tweet_id)
    row["text"] = _valid_text()
    row.update(overrides)
    return row


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Short", False),
        ("x" * 49, False),
        ("x" * 50, True),
        ("x" * 280, True),
        ("x" * 281, False),
    ],
)
def test_check_if_valid_twitter_post_length(text: str, expected: bool) -> None:
    assert twitter_validators.check_if_valid_twitter_post_length(text) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Hello world " + "x" * 40, True),
        (
            "Check this link https://t.co/abc123 " + "x" * 20,
            True,
        ),
        (
            "Visit https://example.com for details " + "x" * 10,
            False,
        ),
        (
            "Shared link https://t.co/xyz in this tweet body " + "x" * 15,
            True,
        ),
    ],
)
def test_check_if_twitter_text_has_no_external_urls(text: str, expected: bool) -> None:
    assert twitter_validators.check_if_twitter_text_has_no_external_urls(text) is expected


def test_strip_tco_links_removes_tco_urls() -> None:
    text = "Before https://t.co/abc after http://t.co/xyz end"
    assert twitter_validators.strip_tco_links(text) == "Before  after  end"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Hello https://t.co/abc", True),
        ("Hello https://example.com", False),
        ("no links " + "x" * 40, False),
    ],
)
def test_has_tco_links(text: str, expected: bool) -> None:
    assert twitter_validators.has_tco_links(text) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (_valid_text(), True),
        ("Bonjour tout le monde, ceci est un tweet en français assez long.", False),
    ],
)
def test_twitter_text_validators(text: str, expected: bool) -> None:
    assert preprocess_twitter.passes_all_validators(text) is expected


def test_filter_posts_drops_invalid_rows() -> None:
    posts = pd.DataFrame(
        [
            _tweet_row(tweet_id="1000000000000000001"),
            _tweet_row(tweet_id="1000000000000000002", text="too short"),
            _tweet_row(
                tweet_id="1000000000000000003",
                text=_valid_text() + " https://example.com/extra",
            ),
        ]
    )
    filtered = preprocess_twitter.filter_posts(posts)
    assert len(filtered) == 1
    assert filtered.iloc[0]["tweet_id"] == "1000000000000000001"


def test_preprocess_records_writes_output(data_root) -> None:
    dataset_id = VALID_TWITTER_DATASET_ID
    raw_storage = TwitterStorageManager("raw", dataset_id)
    run_dir = raw_storage.create_new_run_dir("2026_05_31-10:00:00")
    raw_storage.write_records(
        [
            _tweet_row(tweet_id="1000000000000000001"),
            _tweet_row(tweet_id="1000000000000000002", text="x" * 10),
        ],
        run_dir,
    )
    raw_storage.write_run_metadata(
        run_dir,
        {
            "sync_status": "completed",
            "row_count": 2,
        },
    )

    output_dir = preprocess_twitter.preprocess_records(dataset_id)

    preprocessed_storage = TwitterStorageManager("preprocessed", dataset_id)
    output = preprocessed_storage.load_records(output_dir)
    metadata = preprocessed_storage.load_run_metadata(output_dir)

    assert len(output) == 1
    assert output.iloc[0]["tweet_id"] == "1000000000000000001"
    assert metadata["row_counts"]["input"] == 2
    assert metadata["row_counts"]["output"] == 1
    assert metadata["files"]["posts"] == "posts.csv"


def test_preprocess_records_strips_tco_from_saved_text(data_root) -> None:
    dataset_id = VALID_TWITTER_DATASET_ID
    raw_storage = TwitterStorageManager("raw", dataset_id)
    run_dir = raw_storage.create_new_run_dir("2026_05_31-11:00:00")
    text_with_tco = _valid_text() + " https://t.co/abc123"
    row = _tweet_row(tweet_id="1000000000000000001", text=text_with_tco)
    raw_storage.write_records([row], run_dir)
    raw_storage.write_run_metadata(
        run_dir,
        {
            "sync_status": "completed",
            "row_count": 1,
        },
    )

    output_dir = preprocess_twitter.preprocess_records(dataset_id)

    preprocessed_storage = TwitterStorageManager("preprocessed", dataset_id)
    output = preprocessed_storage.load_records(output_dir)

    assert len(output) == 1
    assert not twitter_validators.has_tco_links(output.iloc[0]["text"])
    assert "https://t.co/" not in output.iloc[0]["text"]
    assert output.iloc[0]["tweet_id"] == row["tweet_id"]
    assert output.iloc[0]["url"] == row["url"]


def test_preprocess_records_merges_all_raw_runs_and_sets_source_raw_runs(data_root) -> None:
    dataset_id = VALID_TWITTER_DATASET_ID
    raw_storage = TwitterStorageManager("raw", dataset_id)

    older_run = raw_storage.create_new_run_dir("2026_05_31-11:00:00")
    newer_run = raw_storage.create_new_run_dir("2026_05_31-12:00:00")

    shared_tweet_id = "1000000000000000001"
    older_text = _valid_text() + " (older run)"
    newer_text = _valid_text() + " (newer run)"

    raw_storage.write_records(
        [_tweet_row(tweet_id=shared_tweet_id, text=older_text)],
        older_run,
    )
    raw_storage.write_run_metadata(
        older_run,
        {
            "sync_status": "completed",
            "row_count": 1,
        },
    )

    raw_storage.write_records(
        [_tweet_row(tweet_id=shared_tweet_id, text=newer_text)],
        newer_run,
    )
    raw_storage.write_run_metadata(
        newer_run,
        {
            "sync_status": "completed",
            "row_count": 1,
        },
    )

    output_dir = preprocess_twitter.preprocess_records(dataset_id)
    preprocessed_storage = TwitterStorageManager("preprocessed", dataset_id)
    output_df = preprocessed_storage.load_records(output_dir)
    metadata = preprocessed_storage.load_run_metadata(output_dir)

    assert len(output_df) == 1
    assert output_df.iloc[0]["tweet_id"] == shared_tweet_id
    # Newest wins: we keep the row from the newer run after deduping.
    assert output_df.iloc[0]["text"] == newer_text

    assert "source_raw_runs" in metadata
    assert len(metadata["source_raw_runs"]) == 2
    assert metadata["source_raw_runs"][-1] == metadata["source_raw_run"]

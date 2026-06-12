from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from data_platform.ingestion.dedupe import increment_metadata_counter, load_prior_seen_ids, persist_deduped_rows
from data_platform.utils.storage import StorageStage, TwitterStorageManager
from tests.data_platform.constants import VALID_TWITTER_DATASET_ID
from tests.data_platform.ingestion.twitter_conftest import mock_tweet_row


@pytest.fixture
def storage() -> MagicMock:
    mock = MagicMock()
    mock.load_seen_ids_from_platform_raw_runs.return_value = {"platform_id"}
    mock.load_seen_ids_from_prior_runs.return_value = {"dataset_id"}
    return mock


def test_load_prior_seen_ids_defaults_to_platform_scan(storage: MagicMock) -> None:
    output_dir = Path("/tmp/run")
    ingestion_params: dict[str, str] = {}

    seen = load_prior_seen_ids(
        storage,
        output_dir,
        ingestion_params,
        "comment_fullname",
        filename="comments.csv",
        same_dataset_flag="dedupe_comments_from_prior_raw_runs",
    )

    assert seen == {"platform_id"}
    storage.load_seen_ids_from_platform_raw_runs.assert_called_once_with(
        output_dir, "comment_fullname", filename="comments.csv"
    )
    storage.load_seen_ids_from_prior_runs.assert_not_called()


def test_load_prior_seen_ids_same_dataset_when_opted_out(storage: MagicMock) -> None:
    output_dir = Path("/tmp/run")
    ingestion_params = {
        "dedupe_across_datasets": False,
        "dedupe_comments_from_prior_raw_runs": True,
    }

    seen = load_prior_seen_ids(
        storage,
        output_dir,
        ingestion_params,
        "comment_fullname",
        filename="comments.csv",
        same_dataset_flag="dedupe_comments_from_prior_raw_runs",
    )

    assert seen == {"dataset_id"}
    storage.load_seen_ids_from_prior_runs.assert_called_once_with(
        output_dir, "comment_fullname", filename="comments.csv"
    )
    storage.load_seen_ids_from_platform_raw_runs.assert_not_called()


def test_increment_metadata_counter() -> None:
    metadata: dict[str, int] = {"posts_skipped_as_duplicates": 2}
    increment_metadata_counter(metadata, "posts_skipped_as_duplicates", 3)
    assert metadata["posts_skipped_as_duplicates"] == 5


def test_persist_deduped_rows_updates_metadata(data_root) -> None:
    storage = TwitterStorageManager(StorageStage.RAW, VALID_TWITTER_DATASET_ID)
    run_dir = storage.create_new_run_dir("2026_05_30-10:00:00")
    metadata: dict[str, int] = {}
    rows = [mock_tweet_row("1"), mock_tweet_row("2")]

    new_rows = persist_deduped_rows(
        storage,
        run_dir,
        rows,
        "tweet_id",
        metadata,
        prior_ids=set(),
        skipped_key="tweets_skipped_as_duplicates",
    )

    assert len(new_rows) == 2
    assert metadata["row_count"] == 2
    assert metadata["tweets_skipped_as_duplicates"] == 0


def test_load_prior_seen_ids_empty_when_both_disabled(storage: MagicMock) -> None:
    output_dir = Path("/tmp/run")
    ingestion_params = {
        "dedupe_across_datasets": False,
        "dedupe_comments_from_prior_raw_runs": False,
    }

    seen = load_prior_seen_ids(
        storage,
        output_dir,
        ingestion_params,
        "comment_fullname",
        filename="comments.csv",
        same_dataset_flag="dedupe_comments_from_prior_raw_runs",
    )

    assert seen == set()
    storage.load_seen_ids_from_platform_raw_runs.assert_not_called()
    storage.load_seen_ids_from_prior_runs.assert_not_called()

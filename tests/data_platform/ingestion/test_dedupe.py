from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from data_platform.ingestion.dedupe import load_prior_seen_ids


@pytest.fixture
def storage() -> MagicMock:
    mock = MagicMock()
    mock.load_seen_ids_from_platform_raw_runs.return_value = {"platform_id"}
    mock.load_seen_ids_from_prior_runs.return_value = {"dataset_id"}
    return mock


def test_load_prior_seen_ids_defaults_to_platform_scan(storage: MagicMock) -> None:
    output_dir = Path("/tmp/run")
    fetch: dict[str, str] = {}

    seen = load_prior_seen_ids(
        storage,
        output_dir,
        fetch,
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
    fetch = {
        "dedupe_across_datasets": False,
        "dedupe_comments_from_prior_raw_runs": True,
    }

    seen = load_prior_seen_ids(
        storage,
        output_dir,
        fetch,
        "comment_fullname",
        filename="comments.csv",
        same_dataset_flag="dedupe_comments_from_prior_raw_runs",
    )

    assert seen == {"dataset_id"}
    storage.load_seen_ids_from_prior_runs.assert_called_once_with(
        output_dir, "comment_fullname", filename="comments.csv"
    )
    storage.load_seen_ids_from_platform_raw_runs.assert_not_called()


def test_load_prior_seen_ids_empty_when_both_disabled(storage: MagicMock) -> None:
    output_dir = Path("/tmp/run")
    fetch = {
        "dedupe_across_datasets": False,
        "dedupe_comments_from_prior_raw_runs": False,
    }

    seen = load_prior_seen_ids(
        storage,
        output_dir,
        fetch,
        "comment_fullname",
        filename="comments.csv",
        same_dataset_flag="dedupe_comments_from_prior_raw_runs",
    )

    assert seen == set()
    storage.load_seen_ids_from_platform_raw_runs.assert_not_called()
    storage.load_seen_ids_from_prior_runs.assert_not_called()

from __future__ import annotations

import pytest

from data_platform.utils.dataset import (
    dataset_root,
    load_dataset_manifest,
    validate_dataset_id,
    write_dataset_manifest,
)
from tests.data_platform.constants import VALID_DATASET_ID


def test_validate_dataset_id_accepts_valid_format() -> None:
    assert validate_dataset_id(VALID_DATASET_ID) == VALID_DATASET_ID


def test_validate_dataset_id_accepts_reddit_format() -> None:
    reddit_id = "reddit_00000000-0000-4000-8000-000000000001"
    assert validate_dataset_id(reddit_id) == reddit_id


def test_validate_dataset_id_accepts_twitter_format() -> None:
    twitter_id = "twitter_00000000-0000-4000-8000-000000000001"
    assert validate_dataset_id(twitter_id) == twitter_id


@pytest.mark.parametrize(
    "invalid",
    [
        "bluesky_not-a-uuid",
        "twitter_not-a-uuid",
        "bluesky_00000000-0000-4000-8000-000000000001-extra",
    ],
)
def test_validate_dataset_id_rejects_invalid(invalid: str) -> None:
    with pytest.raises(ValueError, match="dataset_id must match"):
        validate_dataset_id(invalid)


def test_dataset_root_resolves_under_data_root(data_root) -> None:
    root = dataset_root("bluesky", VALID_DATASET_ID)
    assert root == data_root / "bluesky" / VALID_DATASET_ID


def test_write_and_load_dataset_manifest(data_root) -> None:
    path = write_dataset_manifest(
        "bluesky",
        VALID_DATASET_ID,
        name="mirrorview",
        ingestion_config="data_platform/ingestion/configs/bluesky/mirrorview.yaml",
        created_at="2026-05-29T12:00:00+00:00",
    )
    assert path.exists()
    loaded = load_dataset_manifest("bluesky", VALID_DATASET_ID)
    assert loaded["dataset_id"] == VALID_DATASET_ID
    assert loaded["name"] == "mirrorview"

from __future__ import annotations

from pathlib import Path

import pytest

from data_platform.utils.dataset import (
    dataset_root,
    load_dataset_manifest,
    validate_dataset_id,
    write_dataset_manifest,
)

VALID_ID = "bluesky_00000000-0000-4000-8000-000000000001"


def test_validate_dataset_id_accepts_valid_format() -> None:
    assert validate_dataset_id(VALID_ID) == VALID_ID


@pytest.mark.parametrize(
    "invalid",
    [
        "bluesky_not-a-uuid",
        "twitter_00000000-0000-4000-8000-000000000001",
        "bluesky_00000000-0000-4000-8000-000000000001-extra",
    ],
)
def test_validate_dataset_id_rejects_invalid(invalid: str) -> None:
    with pytest.raises(ValueError, match="dataset_id must match"):
        validate_dataset_id(invalid)


def test_dataset_root_resolves_under_data_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "data_platform.utils.dataset._DATA_ROOT",
        tmp_path,
    )
    root = dataset_root("bluesky", VALID_ID)
    assert root == tmp_path / "bluesky" / VALID_ID


def test_write_and_load_dataset_manifest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "data_platform.utils.dataset._DATA_ROOT",
        tmp_path,
    )
    path = write_dataset_manifest(
        "bluesky",
        VALID_ID,
        name="mirrorview",
        ingestion_config="data_platform/ingestion/configs/bluesky/mirrorview.yaml",
        created_at="2026-05-29T12:00:00+00:00",
    )
    assert path.exists()
    loaded = load_dataset_manifest("bluesky", VALID_ID)
    assert loaded["dataset_id"] == VALID_ID
    assert loaded["name"] == "mirrorview"

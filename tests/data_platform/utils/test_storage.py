from __future__ import annotations

from pathlib import Path

from data_platform.utils.storage import BlueskyStorageManager, DATA_ROOT

VALID_ID = "bluesky_00000000-0000-4000-8000-000000000001"


def test_bluesky_storage_root_includes_dataset_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("data_platform.utils.storage.DATA_ROOT", tmp_path)
    storage = BlueskyStorageManager("raw", VALID_ID)
    assert storage.root_dir == tmp_path / "bluesky" / VALID_ID / "raw"


def test_latest_run_dir_scoped_to_dataset(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("data_platform.utils.storage.DATA_ROOT", tmp_path)
    other_id = "bluesky_00000000-0000-4000-8000-000000000002"
    storage_a = BlueskyStorageManager("raw", VALID_ID)
    storage_b = BlueskyStorageManager("raw", other_id)

    run_a = storage_a.create_new_run_dir("2026_05_29-10:00:00")
    storage_b.create_new_run_dir("2026_05_29-11:00:00")

    assert storage_a.latest_run_dir() == run_a

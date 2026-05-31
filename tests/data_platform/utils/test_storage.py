from __future__ import annotations

import json
from pathlib import Path

from data_platform.utils.storage import BlueskyStorageManager

VALID_ID = "bluesky_00000000-0000-4000-8000-000000000001"

SAMPLE_ROW = {
    "uri": "at://did:plc:example/app.bsky.feed.post/abc",
    "url": "https://bsky.app/profile/handle/post/abc",
    "author_handle": "handle",
    "text": "hello",
    "created_at": "2026-05-30T00:00:00.000Z",
    "like_count": 1,
    "repost_count": 0,
    "reply_count": 0,
    "quote_count": 0,
}


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


def test_append_records_writes_header_once(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("data_platform.utils.storage.DATA_ROOT", tmp_path)
    storage = BlueskyStorageManager("raw", VALID_ID)
    run_dir = storage.create_new_run_dir("2026_05_30-10:00:00")

    storage.append_records([SAMPLE_ROW], run_dir)
    second_row = {**SAMPLE_ROW, "uri": "at://did:plc:example/app.bsky.feed.post/def"}
    storage.append_records([second_row], run_dir)

    csv_path = run_dir / "posts.csv"
    lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0].startswith("uri,")
    assert len(lines) == 3


def test_load_seen_uris(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("data_platform.utils.storage.DATA_ROOT", tmp_path)
    storage = BlueskyStorageManager("raw", VALID_ID)
    run_dir = storage.create_new_run_dir("2026_05_30-10:00:00")
    storage.append_records([SAMPLE_ROW], run_dir)

    assert storage.load_seen_uris(run_dir) == {SAMPLE_ROW["uri"]}


def test_write_run_metadata_atomic(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("data_platform.utils.storage.DATA_ROOT", tmp_path)
    storage = BlueskyStorageManager("raw", VALID_ID)
    run_dir = storage.create_new_run_dir("2026_05_30-10:00:00")
    payload = {"sync_status": "in_progress", "row_count": 0}

    storage.write_run_metadata_atomic(run_dir, payload)
    metadata_path = run_dir / "metadata.json"
    assert not (run_dir / "metadata.json.tmp").exists()
    assert json.loads(metadata_path.read_text(encoding="utf-8")) == payload

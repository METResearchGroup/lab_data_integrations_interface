from __future__ import annotations

import json

from tests.data_platform.constants import VALID_DATASET_ID
from tests.data_platform.conftest import make_ingestion_row


def test_bluesky_storage_root_includes_dataset_id(data_root, bluesky_storage) -> None:
    assert bluesky_storage.root_dir == data_root / "bluesky" / VALID_DATASET_ID / "raw"


def test_latest_run_dir_scoped_to_dataset(data_root, bluesky_storage) -> None:
    other_id = "bluesky_00000000-0000-4000-8000-000000000002"
    from data_platform.utils.storage import BlueskyStorageManager

    storage_b = BlueskyStorageManager("raw", other_id)

    run_a = bluesky_storage.create_new_run_dir("2026_05_29-10:00:00")
    storage_b.create_new_run_dir("2026_05_29-11:00:00")

    assert bluesky_storage.latest_run_dir() == run_a


def test_append_records_writes_header_once(bluesky_storage) -> None:
    run_dir = bluesky_storage.create_new_run_dir("2026_05_30-10:00:00")

    bluesky_storage.append_records([make_ingestion_row()], run_dir)
    second_row = make_ingestion_row(uri="at://did:plc:example/app.bsky.feed.post/def")
    bluesky_storage.append_records([second_row], run_dir)

    csv_path = run_dir / "posts.csv"
    lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0].startswith("uri,")
    assert len(lines) == 3


def test_load_seen_uris(bluesky_storage) -> None:
    run_dir = bluesky_storage.create_new_run_dir("2026_05_30-10:00:00")
    row = make_ingestion_row()
    bluesky_storage.append_records([row], run_dir)

    assert bluesky_storage.load_seen_uris(run_dir) == {row["uri"]}


def test_write_run_metadata_atomic(bluesky_storage) -> None:
    run_dir = bluesky_storage.create_new_run_dir("2026_05_30-10:00:00")
    payload = {"sync_status": "in_progress", "row_count": 0}

    bluesky_storage.write_run_metadata_atomic(run_dir, payload)
    metadata_path = run_dir / "metadata.json"
    assert not (run_dir / "metadata.json.tmp").exists()
    assert json.loads(metadata_path.read_text(encoding="utf-8")) == payload

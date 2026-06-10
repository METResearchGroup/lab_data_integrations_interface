from __future__ import annotations

import json

from data_platform.utils.storage import RedditStorageManager
from tests.data_platform.conftest import make_ingestion_row
from tests.data_platform.constants import VALID_DATASET_ID, VALID_REDDIT_DATASET_ID
from tests.data_platform.ingestion.reddit_conftest import mock_comment_row


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


def test_load_seen_ids_from_prior_runs(data_root) -> None:
    comment_storage = RedditStorageManager("raw", VALID_REDDIT_DATASET_ID)
    prior_run_a = comment_storage.create_new_run_dir("2026_05_29-10:00:00")
    prior_run_b = comment_storage.create_new_run_dir("2026_05_29-11:00:00")
    current_run = comment_storage.create_new_run_dir("2026_05_30-10:00:00")

    comment_storage.append_records(
        [mock_comment_row("t1_comment_a")],
        prior_run_a,
        filename="comments.csv",
    )
    comment_storage.append_records(
        [mock_comment_row("t1_comment_b")],
        prior_run_b,
        filename="comments.csv",
    )
    comment_storage.append_records(
        [mock_comment_row("t1_comment_current")],
        current_run,
        filename="comments.csv",
    )

    seen = comment_storage.load_seen_ids_from_prior_runs(
        current_run,
        "comment_fullname",
        filename="comments.csv",
    )
    assert seen == {"t1_comment_a", "t1_comment_b"}


def test_load_seen_ids_from_platform_raw_runs(data_root) -> None:
    dataset_a = "reddit_00000000-0000-4000-8000-000000000001"
    dataset_b = "reddit_00000000-0000-4000-8000-000000000002"
    storage_a = RedditStorageManager("raw", dataset_a)
    storage_b = RedditStorageManager("raw", dataset_b)

    prior_run_a = storage_a.create_new_run_dir("2026_05_29-10:00:00")
    current_run_b = storage_b.create_new_run_dir("2026_05_30-10:00:00")

    storage_a.append_records(
        [mock_comment_row("t1_comment_a")],
        prior_run_a,
        filename="comments.csv",
    )
    storage_b.append_records(
        [mock_comment_row("t1_comment_b")],
        current_run_b,
        filename="comments.csv",
    )

    seen = storage_b.load_seen_ids_from_platform_raw_runs(
        current_run_b,
        "comment_fullname",
        filename="comments.csv",
    )
    assert seen == {"t1_comment_a"}


def test_write_run_metadata_atomic(bluesky_storage) -> None:
    run_dir = bluesky_storage.create_new_run_dir("2026_05_30-10:00:00")
    payload = {"sync_status": "in_progress", "row_count": 0}

    bluesky_storage.write_run_metadata_atomic(run_dir, payload)
    metadata_path = run_dir / "metadata.json"
    assert not (run_dir / "metadata.json.tmp").exists()
    assert json.loads(metadata_path.read_text(encoding="utf-8")) == payload

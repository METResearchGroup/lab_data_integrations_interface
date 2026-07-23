from __future__ import annotations

import json
from pathlib import Path

import pytest

from data_platform.ingestion.jetstream_cursor import (
    DISK_FORMAT_VERSION,
    JetstreamCursorError,
    JetstreamDiskCursor,
    build_backup_item,
    read_disk_cursor,
    restore_disk_cursor_from_backup_item,
    write_disk_cursor,
)


def _sample_disk() -> JetstreamDiskCursor:
    return JetstreamDiskCursor(
        format_version=DISK_FORMAT_VERSION,
        cursor=1_700_000_000_000_000,
        updated_at="2026-07-23T12:00:00+00:00",
    )


def test_write_and_read_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "cursor.json"
    write_disk_cursor(path, _sample_disk())
    assert read_disk_cursor(path) == _sample_disk()


def test_read_missing_file(tmp_path: Path) -> None:
    with pytest.raises(JetstreamCursorError, match="not found"):
        read_disk_cursor(tmp_path / "missing.json")


def test_read_corrupt_json(tmp_path: Path) -> None:
    path = tmp_path / "cursor.json"
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(JetstreamCursorError, match="invalid JSON"):
        read_disk_cursor(path)


def test_rejects_negative_cursor(tmp_path: Path) -> None:
    path = tmp_path / "cursor.json"
    path.write_text(
        json.dumps(
            {
                "format_version": DISK_FORMAT_VERSION,
                "cursor": -1,
                "updated_at": "2026-07-23T12:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(JetstreamCursorError, match="cursor"):
        read_disk_cursor(path)


def test_rejects_naive_updated_at(tmp_path: Path) -> None:
    path = tmp_path / "cursor.json"
    path.write_text(
        json.dumps(
            {
                "format_version": DISK_FORMAT_VERSION,
                "cursor": 1,
                "updated_at": "2026-07-23T12:00:00",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(JetstreamCursorError, match="timezone-aware"):
        read_disk_cursor(path)


def test_build_backup_item_includes_content_hash() -> None:
    item = build_backup_item(
        _sample_disk(),
        backup_key="bluesky_jetstream_cursor_latest",
        source_path="/tmp/cursor.json",
        backed_up_at="2026-07-23T14:00:00+00:00",
    )
    assert item["cursor"] == 1_700_000_000_000_000
    assert item["content_sha256"]
    assert item["schema_version"] == 1


def test_restore_from_backup_item(tmp_path: Path) -> None:
    item = build_backup_item(
        _sample_disk(),
        backup_key="bluesky_jetstream_cursor_latest",
        source_path="/tmp/cursor.json",
        backed_up_at="2026-07-23T14:00:00+00:00",
    )
    dest = tmp_path / "restored.json"
    disk = restore_disk_cursor_from_backup_item(item, dest)
    assert disk.cursor == 1_700_000_000_000_000
    assert read_disk_cursor(dest) == disk


def test_restore_rejects_checksum_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "cursor.json"
    path.write_text("keep-me", encoding="utf-8")
    item = {
        "backup_key": "bluesky_jetstream_cursor_latest",
        "cursor": 1,
        "format_version": DISK_FORMAT_VERSION,
        "schema_version": 1,
        "backed_up_at": "2026-07-23T14:00:00+00:00",
        "disk_updated_at": "2026-07-23T12:00:00+00:00",
        "source_path": "/tmp/cursor.json",
        "content_sha256": "deadbeef",
    }
    with pytest.raises(JetstreamCursorError, match="content_sha256"):
        restore_disk_cursor_from_backup_item(item, path)
    assert path.read_text(encoding="utf-8") == "keep-me"

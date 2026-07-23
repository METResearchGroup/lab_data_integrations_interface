from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from data_platform.aws.constants import CURSOR_BACKUP_TABLE, JETSTREAM_CURSOR_BACKUP_KEY
from data_platform.ingestion.backup_jetstream_cursor import (
    FAILURE_MARKER,
    SUCCESS_MARKER,
    app,
    run_backup,
)
from data_platform.ingestion.jetstream_cursor import (
    DISK_FORMAT_VERSION,
    JetstreamDiskCursor,
    build_backup_item,
    write_disk_cursor,
)

runner = CliRunner()


@pytest.fixture
def cursor_path(tmp_path: Path) -> Path:
    path = tmp_path / "cursor.json"
    write_disk_cursor(
        path,
        JetstreamDiskCursor(
            format_version=DISK_FORMAT_VERSION,
            cursor=1_700_000_000_000_000,
            updated_at="2026-07-23T12:00:00+00:00",
        ),
    )
    return path


def test_run_backup_puts_full_item(cursor_path: Path) -> None:
    dynamodb = MagicMock()
    result = run_backup(cursor_path, dynamodb, clock=lambda: "2026-07-23T14:00:00+00:00")
    assert result.ok
    dynamodb.put_item.assert_called_once()
    table, item = dynamodb.put_item.call_args.args
    assert table == CURSOR_BACKUP_TABLE
    assert item["backup_key"] == JETSTREAM_CURSOR_BACKUP_KEY
    assert item["cursor"] == 1_700_000_000_000_000
    assert item["backed_up_at"] == "2026-07-23T14:00:00+00:00"
    assert item["disk_updated_at"] == "2026-07-23T12:00:00+00:00"
    assert item["content_sha256"]


def test_run_backup_missing_disk_does_not_put(tmp_path: Path) -> None:
    dynamodb = MagicMock()
    result = run_backup(tmp_path / "missing.json", dynamodb)
    assert not result.ok
    dynamodb.put_item.assert_not_called()


def test_run_backup_dynamodb_failure_leaves_no_second_write(cursor_path: Path) -> None:
    dynamodb = MagicMock()
    dynamodb.put_item.side_effect = RuntimeError("throttled")
    result = run_backup(cursor_path, dynamodb)
    assert not result.ok
    assert "dynamodb write failed" in result.message
    assert dynamodb.put_item.call_count == 1


def test_cli_backup_exit_codes(cursor_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dynamodb = MagicMock()
    monkeypatch.setattr(
        "data_platform.ingestion.backup_jetstream_cursor.DynamoDB",
        lambda: dynamodb,
    )
    ok = runner.invoke(app, ["backup", "--cursor-path", str(cursor_path)])
    assert ok.exit_code == 0

    dynamodb.put_item.side_effect = RuntimeError("boom")
    bad = runner.invoke(app, ["backup", "--cursor-path", str(cursor_path)])
    assert bad.exit_code == 1


def test_cli_restore_from_item_file(tmp_path: Path, cursor_path: Path) -> None:
    disk = JetstreamDiskCursor(
        format_version=DISK_FORMAT_VERSION,
        cursor=42,
        updated_at="2026-07-23T12:00:00+00:00",
    )
    item = build_backup_item(
        disk,
        backup_key=JETSTREAM_CURSOR_BACKUP_KEY,
        source_path=str(cursor_path),
        backed_up_at="2026-07-23T14:00:00+00:00",
    )
    item_path = tmp_path / "backup_item.json"
    item_path.write_text(__import__("json").dumps(item), encoding="utf-8")
    dest = tmp_path / "restored.json"
    result = runner.invoke(
        app,
        [
            "restore-from-item-file",
            "--item-path",
            str(item_path),
            "--cursor-path",
            str(dest),
        ],
    )
    assert result.exit_code == 0
    assert dest.is_file()


def test_log_markers_defined() -> None:
    assert "succeeded" in SUCCESS_MARKER
    assert "failed" in FAILURE_MARKER

"""On-disk Bluesky Jetstream cursor contract (format_version 1).

Disk is the hot-path source of truth. DynamoDB backups (see
``backup_jetstream_cursor``) are a cold disaster-recovery mirror only.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

DISK_FORMAT_VERSION = 1
BACKUP_SCHEMA_VERSION = 1


class JetstreamCursorError(ValueError):
    """Raised when a disk cursor or backup item fails validation."""


@dataclass(frozen=True, slots=True)
class JetstreamDiskCursor:
    format_version: int
    cursor: int
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_version": self.format_version,
            "cursor": self.cursor,
            "updated_at": self.updated_at,
        }


def compute_content_sha256(*, format_version: int, cursor: int, disk_updated_at: str) -> str:
    payload = f"{format_version}:{cursor}:{disk_updated_at}".encode()
    return hashlib.sha256(payload).hexdigest()


def _require_aware_iso8601(value: str, *, field: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise JetstreamCursorError(
            f"{field} must be timezone-aware ISO-8601, got {value!r}"
        ) from exc
    if parsed.tzinfo is None:
        raise JetstreamCursorError(
            f"{field} must be timezone-aware ISO-8601, got {value!r}"
        )
    return value


def validate_disk_cursor_dict(data: Any) -> JetstreamDiskCursor:
    if not isinstance(data, dict):
        raise JetstreamCursorError("disk cursor must be a JSON object")
    format_version = data.get("format_version")
    cursor = data.get("cursor")
    updated_at = data.get("updated_at")
    if format_version != DISK_FORMAT_VERSION:
        raise JetstreamCursorError(
            f"format_version must be {DISK_FORMAT_VERSION}, got {format_version!r}"
        )
    if not isinstance(cursor, int) or isinstance(cursor, bool) or cursor < 0:
        raise JetstreamCursorError(f"cursor must be a non-negative int, got {cursor!r}")
    if not isinstance(updated_at, str):
        raise JetstreamCursorError(f"updated_at must be a string, got {updated_at!r}")
    _require_aware_iso8601(updated_at, field="updated_at")
    return JetstreamDiskCursor(
        format_version=format_version,
        cursor=cursor,
        updated_at=updated_at,
    )


def read_disk_cursor(path: Path) -> JetstreamDiskCursor:
    if not path.is_file():
        raise JetstreamCursorError(f"disk cursor file not found: {path}")
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise JetstreamCursorError(f"disk cursor file unreadable or invalid JSON: {path}") from exc
    return validate_disk_cursor_dict(data)


def write_disk_cursor(path: Path, cursor: JetstreamDiskCursor) -> None:
    """Atomically write a validated disk cursor (tmp + os.replace)."""
    validated = validate_disk_cursor_dict(cursor.to_dict())
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(validated.to_dict(), indent=2, sort_keys=True) + "\n"
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    os.replace(tmp_path, path)


def validate_backup_item(item: dict[str, Any]) -> dict[str, Any]:
    required = (
        "backup_key",
        "cursor",
        "format_version",
        "schema_version",
        "backed_up_at",
        "disk_updated_at",
        "source_path",
        "content_sha256",
    )
    missing = [key for key in required if key not in item]
    if missing:
        raise JetstreamCursorError(f"backup item missing fields: {missing}")
    if item["schema_version"] != BACKUP_SCHEMA_VERSION:
        raise JetstreamCursorError(
            f"schema_version must be {BACKUP_SCHEMA_VERSION}, got {item['schema_version']!r}"
        )
    if item["format_version"] != DISK_FORMAT_VERSION:
        raise JetstreamCursorError(
            f"format_version must be {DISK_FORMAT_VERSION}, got {item['format_version']!r}"
        )
    cursor = item["cursor"]
    if not isinstance(cursor, int) or isinstance(cursor, bool) or cursor < 0:
        raise JetstreamCursorError(f"cursor must be a non-negative int, got {cursor!r}")
    _require_aware_iso8601(item["backed_up_at"], field="backed_up_at")
    _require_aware_iso8601(item["disk_updated_at"], field="disk_updated_at")
    expected = compute_content_sha256(
        format_version=item["format_version"],
        cursor=item["cursor"],
        disk_updated_at=item["disk_updated_at"],
    )
    if item["content_sha256"] != expected:
        raise JetstreamCursorError("backup item content_sha256 mismatch")
    return item


def build_backup_item(
    disk: JetstreamDiskCursor,
    *,
    backup_key: str,
    source_path: str,
    backed_up_at: str,
) -> dict[str, Any]:
    item = {
        "backup_key": backup_key,
        "cursor": disk.cursor,
        "format_version": disk.format_version,
        "schema_version": BACKUP_SCHEMA_VERSION,
        "backed_up_at": backed_up_at,
        "disk_updated_at": disk.updated_at,
        "source_path": source_path,
        "content_sha256": compute_content_sha256(
            format_version=disk.format_version,
            cursor=disk.cursor,
            disk_updated_at=disk.updated_at,
        ),
    }
    return validate_backup_item(item)


def restore_disk_cursor_from_backup_item(item: dict[str, Any], path: Path) -> JetstreamDiskCursor:
    """Validate a backup item and write the corresponding disk cursor file."""
    validated = validate_backup_item(item)
    disk = JetstreamDiskCursor(
        format_version=validated["format_version"],
        cursor=validated["cursor"],
        updated_at=validated["disk_updated_at"],
    )
    write_disk_cursor(path, disk)
    return disk

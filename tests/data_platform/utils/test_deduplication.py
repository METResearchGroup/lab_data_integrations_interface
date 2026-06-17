from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from data_platform.utils.deduplication import DedupeConfig, DedupeSession


def test_session_warm_calls_local_and_athena_checks() -> None:
    storage = MagicMock()
    storage.load_seen_ids_from_disk.return_value = {"uri-a"}
    storage.load_seen_ids_from_athena.return_value = {"uri-b"}
    config = DedupeConfig(id_column="uri", filename="posts.csv")
    session = DedupeSession(config)
    session.warm(storage, Path("/tmp/run"))

    assert session.seen_ids == {"uri-a", "uri-b"}
    storage.load_seen_ids_from_disk.assert_called_once_with(
        Path("/tmp/run"), "uri", filename="posts.csv"
    )
    storage.load_seen_ids_from_athena.assert_called_once()


def test_session_filter_rows_skips_seen() -> None:
    config = DedupeConfig(id_column="uri")
    session = DedupeSession(config)
    session.seen_ids = {"uri-a"}

    kept, skipped = session.filter_rows(
        [
            {"uri": "uri-a", "text": "dup"},
            {"uri": "uri-b", "text": "new"},
        ]
    )

    assert kept == [{"uri": "uri-b", "text": "new"}]
    assert skipped == 1


def test_note_appended_updates_seen_ids() -> None:
    config = DedupeConfig(id_column="uri")
    session = DedupeSession(config)
    session.seen_ids = {"uri-a"}

    session.note_appended([{"uri": "uri-b"}, {"uri": "uri-c"}])

    assert session.seen_ids == {"uri-a", "uri-b", "uri-c"}

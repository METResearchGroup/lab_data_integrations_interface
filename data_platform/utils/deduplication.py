from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from data_platform.utils.storage import StorageManager


@dataclass(frozen=True)
class DedupeConfig:
    id_column: str
    filename: str | None = None


@dataclass
class DedupeSession:
    config: DedupeConfig
    seen_ids: set[str]

    def __init__(self, config: DedupeConfig) -> None:
        self.config = config
        self.seen_ids: set[str] = set()

    def warm(self, storage: StorageManager, output_dir: Path) -> None:  # noqa: F821
        seen: set[str] = set()
        seen.update(
            storage.load_seen_ids(
                output_dir,
                self.config.id_column,
                filename=self.config.filename,
            )
        )
        seen.update(storage.load_seen_ids_from_athena())
        self.seen_ids = seen

    def filter_rows(self, rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
        new_rows = [row for row in rows if row[self.config.id_column] not in self.seen_ids]
        skipped = len(rows) - len(new_rows)
        return new_rows, skipped

    def note_appended(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            self.seen_ids.add(row[self.config.id_column])

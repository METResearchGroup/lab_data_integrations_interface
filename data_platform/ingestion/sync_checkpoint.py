"""Shared checkpoint resume helpers for platform sync scripts."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol, TypeVar

from data_platform.utils.storage import StorageManager


class HasLedgerKey(Protocol):
    @property
    def ledger_key(self) -> str: ...


T = TypeVar("T", bound=HasLedgerKey)


def find_resume_run_dir(
    storage: StorageManager,
    *,
    run_dir_name: str | None,
) -> Path:
    if run_dir_name is not None:
        run_dir = storage.root_dir / run_dir_name
        if not run_dir.is_dir():
            raise FileNotFoundError(f"Run directory not found: {run_dir}")
        return run_dir

    if not storage.root_dir.exists():
        raise FileNotFoundError(f"No raw runs found under {storage.root_dir}")

    candidates: list[tuple[str, Path]] = []
    for path in storage.root_dir.iterdir():
        if not path.is_dir():
            continue
        metadata_path = path / "metadata.json"
        if not metadata_path.exists():
            continue
        metadata = storage.load_run_metadata(path)
        if metadata.get("sync_status") == "in_progress":
            candidates.append((path.name, path))

    if not candidates:
        raise FileNotFoundError(
            f"No in-progress raw run found under {storage.root_dir}. "
            "Start a new sync or pass --run-dir."
        )
    return max(candidates, key=lambda item: item[0])[1]


def merge_work_items_with_metadata(
    work_items: Sequence[T],
    metadata: dict[str, Any],
    *,
    ledger_key: str,
    entity_label: str,
) -> list[T]:
    ledger_keys = {item.ledger_key for item in work_items}
    metadata_keys = set(metadata.get(ledger_key, {}))
    missing = ledger_keys - metadata_keys
    extra = metadata_keys - ledger_keys
    if missing or extra:
        raise ValueError(
            f"Config {entity_label} do not match resume metadata "
            f"(missing in metadata: {sorted(missing)}, extra in metadata: {sorted(extra)})"
        )
    return list(work_items)

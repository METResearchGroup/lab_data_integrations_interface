"""Turn a captured Jetstream file into deterministic flush batches.

Batches are cut on the *broker* timestamp carried in each event, not on
wall-clock time during the replay. That makes the batch boundaries a property of
the captured data alone, so two runs on the same capture always produce the same
number of commits containing the same rows -- which is what makes the measured
request counts comparable across configurations.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Generator, Iterable
from pathlib import Path
from typing import Any

from experimentation.iceberg import constants, schemas


def iter_events(capture_path: Path) -> Generator[dict[str, Any], None, None]:
    """Yield decoded events from a gzipped JSONL capture, skipping bad lines."""
    with gzip.open(capture_path, "rt", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def iter_batches(
    events: Iterable[dict[str, Any]],
    flush_seconds: int = constants.DEFAULT_FLUSH_SECONDS,
) -> Generator[tuple[int, dict[str, list[dict[str, Any]]]], None, None]:
    """Group parsed rows into flush windows.

    Yields ``(batch_index, {record_type: rows})``. A window closes as soon as an
    event arrives whose ingest timestamp is ``flush_seconds`` past the window
    start; the final partial window is always emitted.
    """
    buffers: dict[str, list[dict[str, Any]]] = {rt: [] for rt in constants.RECORD_TYPES}
    window_start: float | None = None
    batch_index = 0

    for event in events:
        parsed = schemas.parse_event(event)
        if parsed is None:
            continue
        record_type, row = parsed

        event_time = row["ingested_at"].timestamp()
        if window_start is None:
            window_start = event_time

        if event_time - window_start >= flush_seconds:
            if any(buffers.values()):
                yield batch_index, {rt: rows for rt, rows in buffers.items() if rows}
                batch_index += 1
            buffers = {rt: [] for rt in constants.RECORD_TYPES}
            window_start = event_time

        buffers[record_type].append(row)

    if any(buffers.values()):
        yield batch_index, {rt: rows for rt, rows in buffers.items() if rows}

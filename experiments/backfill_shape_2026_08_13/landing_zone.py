import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from bluesky_ingestion_jetstream.constants import RECORD_TYPES
from bluesky_ingestion_jetstream.schemas.arrow_schemas import RECORD_TYPE_TO_SCHEMA
from experiments.backfill_shape_2026_08_13.constants import LANDING_ZONE_ROOT


def create_run_dir(run_id: str) -> Path:
    run_dir = LANDING_ZONE_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


class BufferSet:
    """Holds one batch's rows in memory until it is flushed to the landing zone.

    Decides nothing about *when* to flush - main drives that off the user count.
    """

    def __init__(self, run_id: str, run_dir: Path) -> None:
        self.run_id = run_id
        self.run_dir = run_dir
        self.rows: dict[str, list[dict]] = {name: [] for name in RECORD_TYPES}
        self.users: list[dict] = []
        self.errors: list[dict] = []
        self.batch_index = 0

    def add(self, user: dict, rows_by_type: dict[str, list[dict]], error: str | None) -> None:
        """Accumulate one user's backfill into the current batch.

        Errored users still join the batch, with no rows - the manifest is the
        record of who was attempted, not only who succeeded.
        """
        counts = {name: len(rows) for name, rows in rows_by_type.items()}
        self.users.append({**user, "record_counts": counts})

        if error:
            self.errors.append({"handle": user["handle"], "did": user["did"], "reason": error})
            return

        for name, rows in rows_by_type.items():
            self.rows[name].extend(rows)

    def flush(self) -> Path | None:
        """Write the batch to disk and reset. Returns the batch dir, or None if
        no users were buffered (a trailing flush on an exact multiple)."""
        if not self.users:
            return None

        self.batch_index += 1
        batch_dir = self.run_dir / f"batch_{self.batch_index:03d}"
        batch_dir.mkdir(parents=True, exist_ok=True)

        for name in RECORD_TYPES:
            rows = self.rows[name]
            if not rows:
                continue
            stamped = [{**row, "run_id": self.run_id} for row in rows]
            table = pa.Table.from_pylist(stamped, schema=RECORD_TYPE_TO_SCHEMA[name])
            pq.write_table(table, batch_dir / f"{name}.parquet")

        manifest = {
            "run_id": self.run_id,
            "batch_index": self.batch_index,
            "users": self.users,
            "record_counts": {name: len(self.rows[name]) for name in RECORD_TYPES},
            "errors": self.errors,
        }
        with open(batch_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        self.rows = {name: [] for name in RECORD_TYPES}
        self.users = []
        self.errors = []
        return batch_dir

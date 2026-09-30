"""Baseline write path: buffer -> Parquet -> S3, no table format at all.

This is the control. Subtracting these numbers from the Iceberg append numbers
gives the metadata tax in isolation: same rows, same Parquet encoder, same
partition layout, the only difference being that nothing tracks a manifest.
"""

from __future__ import annotations

import io
from typing import Any

import boto3
import pyarrow as pa
import pyarrow.parquet as pq

from experimentation.iceberg import constants, schemas


def build_arrow(schema: pa.Schema, rows: list[dict[str, Any]]) -> pa.Table:
    """Project ``rows`` onto an explicit Arrow schema.

    Takes the schema as an argument rather than looking it up, because the
    Iceberg path must build against the *table's* schema -- see the field-id
    note in ``schemas.py``.
    """
    columns = {field.name: [row.get(field.name) for row in rows] for field in schema}
    return pa.Table.from_pydict(columns, schema=schema)


def rows_to_arrow(record_type: str, rows: list[dict[str, Any]]) -> pa.Table:
    """Build an Arrow table from the declared schema for ``record_type``.

    Only for the raw baseline, which never round-trips through Iceberg metadata
    and so is unaffected by field-id assignment.
    """
    return build_arrow(schemas.SCHEMAS[record_type].as_arrow(), rows)


class RawWriter:
    """Writes each flush batch as one Parquet object under a daily prefix."""

    def __init__(self, run_id: str, region: str = constants.AWS_REGION) -> None:
        self.run_id = run_id
        self.client = boto3.client("s3", region_name=region)
        self.bytes_written = 0
        self.objects_written = 0

    def _key(self, record_type: str, day: str, batch_index: int) -> str:
        return (
            f"{constants.S3_EXPERIMENT_PREFIX}/{self.run_id}/raw/"
            f"{record_type}/created_at_day={day}/batch-{batch_index:05d}.parquet"
        )

    def write_batch(self, record_type: str, rows: list[dict[str, Any]], batch_index: int) -> int:
        """Write ``rows`` as Parquet, split by day so the layout matches Iceberg's.

        Returns the number of S3 objects written.
        """
        by_day: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            by_day.setdefault(row["created_at"].strftime("%Y-%m-%d"), []).append(row)

        for day, day_rows in by_day.items():
            table = rows_to_arrow(record_type, day_rows)
            buffer = io.BytesIO()
            pq.write_table(table, buffer, compression="zstd")
            payload = buffer.getvalue()

            self.client.put_object(
                Bucket=constants.S3_BUCKET,
                Key=self._key(record_type, day, batch_index),
                Body=payload,
            )
            self.bytes_written += len(payload)
            self.objects_written += 1

        return len(by_day)

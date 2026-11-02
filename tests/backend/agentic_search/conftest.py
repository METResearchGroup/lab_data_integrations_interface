"""A real, local Iceberg posts table for anything that plans a scan."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pyarrow as pa
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pyiceberg.catalog import Catalog
from pyiceberg.catalog.memory import InMemoryCatalog
from pyiceberg.transforms import DayTransform

from bluesky_ingestion_jetstream.aws.constants import (
    GLUE_DATABASE,
    PARTITION_FIELD_NAME,
    PARTITION_SOURCE_COLUMN,
)
from bluesky_ingestion_jetstream.constants import RecordType
from bluesky_ingestion_jetstream.schemas.arrow_schemas import POST_SCHEMA

# Three days of posts, one file per day.
POST_DAYS = (date(2026, 7, 1), date(2026, 7, 2), date(2026, 7, 3))
POSTS_PER_DAY = 200


def _rows(day: date) -> list[dict]:
    stamp = datetime(day.year, day.month, day.day, 12, tzinfo=UTC)
    return [
        {
            "uri": f"at://did:plc:{index}/app.bsky.feed.post/{day}",
            "did": f"did:plc:{index}",
            "cid": f"cid-{index}",
            "rev": f"rev-{index}",
            "created_at": stamp,
            "ingested_at": stamp,
            "run_id": "test-run",
            # Long enough that `text` dominates the file, so a query that skips
            # it estimates visibly cheaper.
            "text": f"post {index} " + "x" * 500,
            "langs": ["en"],
            "reply_root_uri": None,
            "reply_parent_uri": None,
            "embed_type": None,
        }
        for index in range(POSTS_PER_DAY)
    ]


@pytest.fixture(scope="session")
def _exporter() -> InMemorySpanExporter:
    """The global tracer provider can be set once per process."""

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return exporter


@pytest.fixture
def spans(_exporter: InMemorySpanExporter) -> InMemorySpanExporter:
    _exporter.clear()
    return _exporter


@pytest.fixture
def catalog(tmp_path) -> Catalog:
    """Partitioned the way `bootstrap.create_table` partitions the real tables."""

    catalog = InMemoryCatalog("test", warehouse=f"file://{tmp_path}")
    catalog.create_namespace(GLUE_DATABASE)
    table = catalog.create_table((GLUE_DATABASE, RecordType.POSTS), schema=POST_SCHEMA)
    table.update_spec().add_field(
        PARTITION_SOURCE_COLUMN, DayTransform(), PARTITION_FIELD_NAME
    ).commit()

    for day in POST_DAYS:
        table.append(pa.Table.from_pylist(_rows(day), schema=POST_SCHEMA))

    return catalog

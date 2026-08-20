"""Tests for the catalog snapshot. Runs against fake tables; nothing here touches AWS."""

from datetime import date

import pytest
from pyiceberg.schema import Schema
from pyiceberg.types import ListType, NestedField, StringType, TimestamptzType

from backend.agentic_search.catalog import snapshot as snapshot_module
from backend.agentic_search.catalog.snapshot import build_snapshot, clear_cache, get_catalog
from bluesky_ingestion_jetstream.aws.constants import GLUE_DATABASE, PARTITION_FIELD_NAME
from bluesky_ingestion_jetstream.constants import POSTS

POSTS_SCHEMA = Schema(
    NestedField(1, "uri", StringType(), required=True),
    NestedField(2, "created_at", TimestamptzType(), required=True),
    NestedField(3, "text", StringType(), required=False),
    NestedField(4, "langs", ListType(5, StringType(), element_required=False), required=False),
    NestedField(6, "mystery", StringType(), required=False),
)


def partition(day: date | None, record_count: int, deleted: int = 0) -> dict:
    return {
        "partition": {PARTITION_FIELD_NAME: day},
        "record_count": record_count,
        "position_delete_record_count": deleted,
    }


class FakeInspect:
    def __init__(self, partitions: list[dict]):
        self._partitions = partitions

    def partitions(self):
        class Result:
            def __init__(self, rows):
                self._rows = rows

            def to_pylist(self):
                return self._rows

        return Result(self._partitions)


class FakeTable:
    def __init__(self, partitions: list[dict] | None = None, has_snapshot: bool = True):
        self._has_snapshot = has_snapshot
        self.inspect = FakeInspect(partitions or [])

    def schema(self) -> Schema:
        return POSTS_SCHEMA

    def current_snapshot(self):
        return object() if self._has_snapshot else None


def build_posts(partitions: list[dict] | None = None, has_snapshot: bool = True):
    return build_snapshot({POSTS: FakeTable(partitions, has_snapshot)}).tables[0]


def test_columns_carry_iceberg_types():
    columns = {column.name: column.type for column in build_posts().columns}

    assert columns == {
        "uri": "string",
        "created_at": "timestamptz",
        "text": "string",
        "langs": "list<string>",
        "mystery": "string",
    }


def test_columns_carry_hand_written_descriptions():
    columns = {column.name: column.description for column in build_posts().columns}

    assert columns["text"] == "Post body."
    assert columns["uri"] == "AT Protocol URI of the record."
    assert columns["mystery"] is None


def test_table_identity_and_description():
    table = build_posts()

    assert (table.database, table.name, table.record_type) == (GLUE_DATABASE, POSTS, POSTS)
    assert table.description is not None


def test_coverage_spans_the_days_we_hold():
    table = build_posts(
        [
            partition(date(2026, 5, 14), 2_000_000),
            partition(date(2026, 8, 20), 1_000_000),
        ]
    )

    assert (table.earliest_day, table.latest_day) == (date(2026, 5, 14), date(2026, 8, 20))
    assert table.row_count == 3_000_000


def test_row_count_excludes_deleted_rows():
    table = build_posts([partition(date(2026, 5, 14), 2_000_000, deleted=500_000)])

    assert table.row_count == 1_500_000


def test_null_partition_is_not_a_day():
    table = build_posts([partition(None, 2_000_000)])

    assert (table.earliest_day, table.latest_day) == (None, None)
    assert table.row_count == 2_000_000


def test_table_without_a_snapshot_has_no_coverage():
    table = build_posts(has_snapshot=False)

    assert (table.earliest_day, table.latest_day, table.row_count) == (None, None, 0)


def test_get_table_finds_by_name():
    catalog = build_snapshot({POSTS: FakeTable()})

    assert catalog.get_table(POSTS) is not None
    assert catalog.get_table("nope") is None


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def cached_catalog(monkeypatch):
    """A patched-out `build_snapshot` and a clock the test moves by hand."""

    clock = FakeClock()
    builds = []

    def fake_build():
        builds.append(len(builds))
        return build_snapshot({POSTS: FakeTable()})

    monkeypatch.setattr(snapshot_module, "monotonic", clock)
    monkeypatch.setattr(snapshot_module, "build_snapshot", fake_build)
    clear_cache()
    yield clock, builds
    clear_cache()


def test_catalog_is_cached_within_the_ttl(cached_catalog):
    clock, builds = cached_catalog

    get_catalog()
    clock.now = snapshot_module.CATALOG_TTL_SECONDS - 1
    get_catalog()

    assert len(builds) == 1


def test_catalog_is_rebuilt_after_the_ttl(cached_catalog):
    clock, builds = cached_catalog

    get_catalog()
    clock.now = snapshot_module.CATALOG_TTL_SECONDS
    get_catalog()

    assert len(builds) == 2


def test_force_refresh_rebuilds_immediately(cached_catalog):
    _, builds = cached_catalog

    get_catalog()
    get_catalog(force_refresh=True)

    assert len(builds) == 2

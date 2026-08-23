"""Snapshot building and its TTL cache, with Glue stubbed out."""

from __future__ import annotations

from datetime import date

import pytest

from backend.agentic_search.catalog import snapshot as snapshot_module
from backend.agentic_search.catalog.snapshot import build_snapshot, load_snapshot, reset_cache
from bluesky_ingestion_jetstream.aws.constants import PARTITION_FIELD_NAME
from bluesky_ingestion_jetstream.constants import RecordType

MODULE = "backend.agentic_search.catalog.snapshot"

POST_COLUMNS = ("uri", "did", "cid", "created_at", "text", "langs")
LIKE_COLUMNS = ("uri", "did", "cid", "created_at", "subject_uri")


class _FakeField:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeSchema:
    def __init__(self, columns: tuple[str, ...]) -> None:
        self.fields = [_FakeField(name) for name in columns]


class _FakePartitions:
    def __init__(self, days: list[date]) -> None:
        self._days = days

    def to_pylist(self) -> list[dict]:
        return [{"partition": {PARTITION_FIELD_NAME: day}} for day in self._days]


class _FakeInspect:
    def __init__(self, days: list[date]) -> None:
        self._days = days

    def partitions(self) -> _FakePartitions:
        return _FakePartitions(self._days)


class _FakeTable:
    def __init__(self, columns: tuple[str, ...], days: list[date]) -> None:
        self._columns = columns
        self.inspect = _FakeInspect(days)

    def schema(self) -> _FakeSchema:
        return _FakeSchema(self._columns)


@pytest.fixture(autouse=True)
def _clear_cache():
    reset_cache()
    yield
    reset_cache()


@pytest.fixture
def stub_tables(monkeypatch: pytest.MonkeyPatch):
    """Install fake tables and report how many times Glue was read."""

    calls = {"count": 0}

    def _stub(tables: dict[RecordType, _FakeTable], *, fail: bool = False) -> dict:
        def _load_tables(_catalog):
            calls["count"] += 1
            if fail:
                raise RuntimeError("glue is down")
            return tables

        monkeypatch.setattr(f"{MODULE}.build_catalog", lambda: None)
        monkeypatch.setattr(f"{MODULE}.load_tables", _load_tables)
        return calls

    return _stub


def test_columns_and_coverage_come_from_iceberg(stub_tables) -> None:
    stub_tables(
        {
            RecordType.POSTS: _FakeTable(
                POST_COLUMNS,
                [date(2026, 8, 3), date(2026, 8, 1), date(2026, 8, 2)],
            )
        }
    )
    metadata = build_snapshot()[RecordType.POSTS]

    assert metadata.columns == POST_COLUMNS
    assert metadata.coverage_start == date(2026, 8, 1)
    assert metadata.coverage_end == date(2026, 8, 3)


def test_table_without_partitions_is_omitted(stub_tables) -> None:
    stub_tables(
        {
            RecordType.POSTS: _FakeTable(POST_COLUMNS, [date(2026, 8, 1)]),
            RecordType.REPOSTS: _FakeTable(LIKE_COLUMNS, []),
        }
    )
    snapshot = build_snapshot()

    assert set(snapshot) == {RecordType.POSTS}


def test_snapshot_is_cached_within_the_ttl(stub_tables) -> None:
    calls = stub_tables({RecordType.POSTS: _FakeTable(POST_COLUMNS, [date(2026, 8, 1)])})

    assert load_snapshot() == load_snapshot()
    assert calls["count"] == 1


def test_expired_ttl_rebuilds(stub_tables, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = stub_tables({RecordType.POSTS: _FakeTable(POST_COLUMNS, [date(2026, 8, 1)])})

    load_snapshot()
    monkeypatch.setattr(snapshot_module, "_expires_at", 0.0)
    load_snapshot()

    assert calls["count"] == 2


def test_force_refresh_ignores_the_cache(stub_tables) -> None:
    calls = stub_tables({RecordType.POSTS: _FakeTable(POST_COLUMNS, [date(2026, 8, 1)])})

    load_snapshot()
    load_snapshot(force_refresh=True)

    assert calls["count"] == 2


def test_failed_refresh_serves_the_stale_snapshot(
    stub_tables,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tables = {RecordType.POSTS: _FakeTable(POST_COLUMNS, [date(2026, 8, 1)])}
    stub_tables(tables)
    warm = load_snapshot()

    stub_tables(tables, fail=True)
    monkeypatch.setattr(snapshot_module, "_expires_at", 0.0)

    assert load_snapshot() == warm


def test_cold_start_failure_raises(stub_tables) -> None:
    stub_tables({}, fail=True)

    with pytest.raises(RuntimeError, match="glue is down"):
        load_snapshot()

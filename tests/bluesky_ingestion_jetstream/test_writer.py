"""Tests for the Parquet writer and its path building."""

from datetime import UTC, datetime

import pyarrow.parquet as pq
import pytest

from bluesky_ingestion_jetstream.constants import RECORD_TYPES
from bluesky_ingestion_jetstream.schemas.arrow_schemas import RECORD_TYPE_TO_SCHEMA
from bluesky_ingestion_jetstream.writer import build_path, write


@pytest.fixture
def frozen_clock(monkeypatch):
    """Pin the timestamp so filenames are predictable."""

    from bluesky_ingestion_jetstream import writer

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 7, 23, 6, 48, 11, tzinfo=tz or UTC)

    monkeypatch.setattr(writer, "datetime", FixedDatetime)


class TestBuildPath:
    def test_creates_the_record_type_directory(self, tmp_path):
        build_path("likes", tmp_path)

        assert (tmp_path / "likes").is_dir()

    @pytest.mark.usefixtures("frozen_clock")
    def test_partitions_by_record_type(self, tmp_path):
        path = build_path("likes", tmp_path)

        assert path.parent == tmp_path / "likes"
        assert path.name == "2026_07_23-06:48:11.parquet"

    def test_creates_parent_directories(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c"
        path = build_path("posts", nested)

        assert path.parent.is_dir()

    def test_names_sort_chronologically(self, tmp_path):
        """The repo format is zero-padded, so lexical order is time order."""

        from bluesky_ingestion_jetstream import writer

        names = []
        for moment in [
            datetime(2026, 7, 23, 11, 4, 9, tzinfo=UTC),
            datetime(2026, 7, 23, 6, 48, 11, tzinfo=UTC),
        ]:

            class Fixed(datetime):
                fixed = moment

                @classmethod
                def now(cls, tz=None):
                    return cls.fixed

            original = writer.datetime
            writer.datetime = Fixed
            names.append(build_path("posts", tmp_path).name)
            writer.datetime = original

        assert sorted(names) == [names[1], names[0]]

    @pytest.mark.usefixtures("frozen_clock")
    def test_collision_gets_a_suffix(self, tmp_path):
        """The format resolves to the second, so two flushes can collide."""

        first = build_path("likes", tmp_path)
        first.touch()
        second = build_path("likes", tmp_path)

        assert second.name == "2026_07_23-06:48:11-1.parquet"

    @pytest.mark.usefixtures("frozen_clock")
    def test_repeated_collisions_keep_incrementing(self, tmp_path):
        names = []
        for _ in range(3):
            path = build_path("likes", tmp_path)
            path.touch()
            names.append(path.name)

        assert names == [
            "2026_07_23-06:48:11.parquet",
            "2026_07_23-06:48:11-1.parquet",
            "2026_07_23-06:48:11-2.parquet",
        ]

    @pytest.mark.usefixtures("frozen_clock")
    def test_never_returns_an_existing_path(self, tmp_path):
        """Returning one would silently overwrite a written flush."""

        for _ in range(3):
            path = build_path("likes", tmp_path)
            assert not path.exists()
            path.touch()


class TestWrite:
    @pytest.mark.parametrize("record_type", RECORD_TYPES)
    def test_writes_a_readable_file(self, record_type, rows_factory, tmp_path):
        rows = rows_factory(record_type, 5)
        path = write(record_type, rows, tmp_path)

        table = pq.read_table(path)

        assert path.is_file()
        assert table.num_rows == 5

    @pytest.mark.parametrize("record_type", RECORD_TYPES)
    def test_file_matches_the_declared_schema(self, record_type, rows_factory, tmp_path):
        path = write(record_type, rows_factory(record_type, 3), tmp_path)

        table = pq.read_table(path)

        assert table.schema.equals(RECORD_TYPE_TO_SCHEMA[record_type], check_metadata=False)

    def test_values_survive_the_round_trip(self, rows_factory, tmp_path):
        rows = rows_factory("follows", 3)
        path = write("follows", rows, tmp_path)

        table = pq.read_table(path)

        assert table.column("uri").to_pylist() == [row["uri"] for row in rows]
        assert table.column("subject_did").to_pylist() == [row["subject_did"] for row in rows]
        assert table.column("created_at").to_pylist() == [row["created_at"] for row in rows]

    def test_langs_round_trips_as_a_list(self, rows_factory, tmp_path):
        path = write("posts", rows_factory("posts", 2), tmp_path)

        assert pq.read_table(path).column("langs").to_pylist() == [["en"], ["en"]]

    def test_null_optional_columns_are_written(self, tmp_path):
        """A row whose optional columns are all null must still persist."""

        from bluesky_ingestion_jetstream.network.connection import process_commit_event
        from tests.bluesky_ingestion_jetstream.conftest import POST_COLLECTION, make_event

        parsed = process_commit_event(
            make_event(POST_COLLECTION, {"createdAt": "2026-07-23T06:48:11Z"})
        )
        assert parsed is not None

        table = pq.read_table(write("posts", [parsed[1]], tmp_path))

        assert table.num_rows == 1
        assert table.column("text").to_pylist() == [None]
        assert table.column("langs").to_pylist() == [None]

    def test_returns_the_written_path(self, rows_factory, tmp_path):
        path = write("likes", rows_factory("likes", 1), tmp_path)

        assert path.parent == tmp_path / "likes"
        assert path.suffix == ".parquet"

    def test_successive_writes_do_not_overwrite(self, rows_factory, tmp_path):
        first = write("likes", rows_factory("likes", 2), tmp_path)
        second = write("likes", rows_factory("likes", 3), tmp_path)

        assert first != second
        assert pq.read_table(first).num_rows == 2
        assert pq.read_table(second).num_rows == 3

    def test_empty_rows_write_an_empty_file(self, tmp_path):
        """flush() guards against this, but the writer must not raise on it."""

        table = pq.read_table(write("likes", [], tmp_path))

        assert table.num_rows == 0

    def test_unknown_record_type_raises(self, rows_factory, tmp_path):
        with pytest.raises(KeyError):
            write("blocks", rows_factory("likes", 1), tmp_path)

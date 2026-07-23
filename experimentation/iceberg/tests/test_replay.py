"""Tests for flush-window batching and the dedup rule used during compaction."""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime

import pyarrow as pa

from experimentation.iceberg import replay, schemas
from experimentation.iceberg.maintenance import _collapse_to_latest, _drop_tombstones

BASE_US = 1_784_721_600_000_000  # 2026-07-22T12:00:00Z


def _event(offset_seconds: float, collection: str = "app.bsky.feed.post", rkey: str = "r1") -> dict:
    return {
        "did": "did:plc:alice",
        "time_us": BASE_US + int(offset_seconds * 1_000_000),
        "kind": "commit",
        "commit": {
            "rev": "rev1",
            "operation": "create",
            "collection": collection,
            "rkey": rkey,
            "cid": "bafy",
            "record": {"createdAt": "2026-07-22T12:00:00Z", "text": "x"},
        },
    }


class TestBatching:
    def test_events_inside_one_window_form_a_single_batch(self):
        events = [_event(i, rkey=f"r{i}") for i in range(10)]
        batches = list(replay.iter_batches(events, flush_seconds=60))
        assert len(batches) == 1
        assert len(batches[0][1]["posts"]) == 10

    def test_window_closes_at_the_flush_boundary(self):
        # 0..59s in window 0, 60..119s in window 1, 120s in window 2.
        events = [_event(t, rkey=f"r{t}") for t in (0, 30, 59, 60, 90, 120)]
        batches = list(replay.iter_batches(events, flush_seconds=60))
        assert [len(rows["posts"]) for _, rows in batches] == [3, 2, 1]

    def test_batch_indices_are_sequential(self):
        events = [_event(t, rkey=f"r{t}") for t in (0, 60, 120, 180)]
        assert [index for index, _ in replay.iter_batches(events, flush_seconds=60)] == [0, 1, 2, 3]

    def test_record_types_are_split_within_a_batch(self):
        events = [
            _event(0, "app.bsky.feed.post", "r1"),
            _event(1, "app.bsky.feed.like", "r2"),
            _event(2, "app.bsky.graph.follow", "r3"),
            _event(3, "app.bsky.feed.repost", "r4"),
        ]
        _, buffers = next(iter(replay.iter_batches(events, flush_seconds=60)))
        assert set(buffers) == {"posts", "likes", "follows", "reposts"}
        assert all(len(rows) == 1 for rows in buffers.values())

    def test_empty_record_types_are_omitted(self):
        _, buffers = next(iter(replay.iter_batches([_event(0)], flush_seconds=60)))
        assert set(buffers) == {"posts"}

    def test_trailing_partial_window_is_emitted(self):
        events = [_event(t, rkey=f"r{t}") for t in (0, 60, 61)]
        batches = list(replay.iter_batches(events, flush_seconds=60))
        assert len(batches) == 2
        assert len(batches[1][1]["posts"]) == 2

    def test_no_events_yields_no_batches(self):
        assert list(replay.iter_batches([], flush_seconds=60)) == []

    def test_untracked_events_do_not_open_a_window(self):
        events = [
            {"kind": "identity", "did": "did:plc:alice", "time_us": BASE_US},
            _event(0),
        ]
        batches = list(replay.iter_batches(events, flush_seconds=60))
        assert len(batches) == 1
        assert len(batches[0][1]["posts"]) == 1

    def test_batching_is_deterministic_across_runs(self):
        """The whole point of replaying: identical input must give identical commits."""
        events = [_event(t * 7, rkey=f"r{t}") for t in range(40)]
        first = [
            (i, {k: len(v) for k, v in b.items()}) for i, b in replay.iter_batches(list(events), 60)
        ]
        second = [
            (i, {k: len(v) for k, v in b.items()}) for i, b in replay.iter_batches(list(events), 60)
        ]
        assert first == second


class TestIterEvents:
    def test_reads_gzipped_jsonl(self, tmp_path):
        path = tmp_path / "capture.jsonl.gz"
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            for i in range(3):
                handle.write(json.dumps(_event(i, rkey=f"r{i}")) + "\n")
        assert len(list(replay.iter_events(path))) == 3

    def test_malformed_and_blank_lines_are_skipped(self, tmp_path):
        path = tmp_path / "capture.jsonl.gz"
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            handle.write(json.dumps(_event(0)) + "\n")
            handle.write("{not json\n")
            handle.write("\n")
            handle.write(json.dumps(_event(1, rkey="r2")) + "\n")
        assert len(list(replay.iter_events(path))) == 2


def _arrow_rows(rows: list[dict]) -> pa.Table:
    schema = schemas.SCHEMAS["posts"].as_arrow()
    return pa.Table.from_pydict(
        {f.name: [r.get(f.name) for r in rows] for f in schema}, schema=schema
    )


def _row(
    uri: str,
    ingested_offset: int,
    text: str,
    operation: str = "create",
    cid: str | None = "c",
) -> dict:
    ingested = datetime.fromtimestamp(BASE_US / 1e6 + ingested_offset, tz=UTC)
    return {
        "uri": uri,
        "did": "did:plc:alice",
        "collection": "app.bsky.feed.post",
        "rkey": uri.rsplit("/", 1)[-1],
        "cid": cid,
        "rev": "r",
        "operation": operation,
        "created_at": ingested,
        "ingested_at": ingested,
        "created_at_fallback": False,
        "text": text,
        "langs": None,
        "reply_root_uri": None,
        "reply_parent_uri": None,
        "embed_type": None,
        "text_length": len(text),
    }


class TestCollapseToLatest:
    def test_same_uri_and_cid_is_a_redelivered_duplicate(self):
        """Identical event twice -- the only thing that is really a duplicate."""
        table = _arrow_rows(
            [_row("at://a/1", 0, "same", cid="c1"), _row("at://a/1", 10, "same", cid="c1")]
        )
        collapsed, stats = _collapse_to_latest(table)
        assert stats["redelivered_duplicates"] == 1
        assert stats["lifecycle_collapses"] == 0
        assert collapsed.num_rows == 1

    def test_same_uri_different_cid_is_a_lifecycle_collapse(self):
        """Create then edit -- two real events about one record, not a duplicate."""
        table = _arrow_rows(
            [_row("at://a/1", 0, "v1", cid="c1"), _row("at://a/1", 10, "v2", cid="c2")]
        )
        collapsed, stats = _collapse_to_latest(table)
        assert stats["redelivered_duplicates"] == 0
        assert stats["lifecycle_collapses"] == 1
        assert collapsed.column("text").to_pylist() == ["v2"]

    def test_create_then_delete_counts_as_lifecycle_not_duplicate(self):
        table = _arrow_rows(
            [
                _row("at://a/1", 0, "hello", cid="c1"),
                _row("at://a/1", 10, "", operation="delete", cid=None),
            ]
        )
        collapsed, stats = _collapse_to_latest(table)
        assert stats["redelivered_duplicates"] == 0
        assert stats["lifecycle_collapses"] == 1
        assert collapsed.column("operation").to_pylist() == ["delete"]

    def test_distinct_uris_are_all_kept(self):
        table = _arrow_rows([_row(f"at://a/{i}", i, "t") for i in range(5)])
        collapsed, stats = _collapse_to_latest(table)
        assert stats == {"redelivered_duplicates": 0, "lifecycle_collapses": 0}
        assert collapsed.num_rows == 5

    def test_three_events_keep_only_the_newest(self):
        table = _arrow_rows(
            [
                _row("at://a/1", 0, "v1", cid="c1"),
                _row("at://a/1", 5, "v2", cid="c2"),
                _row("at://a/1", 9, "v3", cid="c3"),
            ]
        )
        collapsed, stats = _collapse_to_latest(table)
        assert stats["lifecycle_collapses"] == 2
        assert collapsed.column("text").to_pylist() == ["v3"]

    def test_empty_table(self):
        collapsed, stats = _collapse_to_latest(_arrow_rows([]))
        assert stats == {"redelivered_duplicates": 0, "lifecycle_collapses": 0}
        assert collapsed.num_rows == 0

    def test_all_columns_survive(self):
        table = _arrow_rows(
            [_row("at://a/1", 0, "old", cid="c1"), _row("at://a/1", 10, "new", cid="c2")]
        )
        collapsed, _ = _collapse_to_latest(table)
        assert collapsed.schema == table.schema


class TestDropTombstones:
    def test_delete_rows_are_removed(self):
        table = _arrow_rows(
            [
                _row("at://a/1", 0, "kept"),
                _row("at://a/2", 1, "", operation="delete", cid=None),
                _row("at://a/3", 2, "kept too"),
            ]
        )
        kept, dropped = _drop_tombstones(table)
        assert dropped == 1
        assert kept.column("uri").to_pylist() == ["at://a/1", "at://a/3"]

    def test_updates_are_not_tombstones(self):
        table = _arrow_rows([_row("at://a/1", 0, "edited", operation="update")])
        kept, dropped = _drop_tombstones(table)
        assert dropped == 0
        assert kept.num_rows == 1

    def test_all_deletes_yields_empty_table(self):
        table = _arrow_rows(
            [_row(f"at://a/{i}", i, "", operation="delete", cid=None) for i in range(3)]
        )
        kept, dropped = _drop_tombstones(table)
        assert dropped == 3
        assert kept.num_rows == 0
        assert kept.schema == table.schema

    def test_empty_table(self):
        kept, dropped = _drop_tombstones(_arrow_rows([]))
        assert dropped == 0
        assert kept.num_rows == 0

    def test_create_delete_pair_vanishes_end_to_end(self):
        """The full compaction rule: collapse to latest, then drop the tombstone."""
        table = _arrow_rows(
            [
                _row("at://a/1", 0, "posted", cid="c1"),
                _row("at://a/1", 10, "", operation="delete", cid=None),
                _row("at://a/2", 5, "survivor", cid="c3"),
            ]
        )
        collapsed, _ = _collapse_to_latest(table)
        final, dropped = _drop_tombstones(collapsed)
        assert dropped == 1
        assert final.column("uri").to_pylist() == ["at://a/2"]

"""Tests for the per-flush log payload.

The counters are OTel's job; what is worth pinning here is the shape of the JSON
the flush table is built from, since a column that appears only sometimes makes
the table unsortable.
"""

import json

from bluesky_ingestion_jetstream.constants import FLUSH_REASON_AGE, FLUSH_REASON_SIZE, RECORD_TYPES
from bluesky_ingestion_jetstream.storage.buffer import FlushSummary
from bluesky_ingestion_jetstream.telemetry.instruments import get_flush_payload, record_flush


def summary(reason=FLUSH_REASON_AGE, rows=None, sizes=None) -> FlushSummary:
    return FlushSummary(reason=reason, rows=rows or {}, sizes=sizes or {})


class TestFlushPayload:
    def test_every_record_type_appears_even_when_empty(self):
        """Otherwise the table's columns shift with whatever happened to be buffered."""

        payload = get_flush_payload(summary(rows={"posts": 3}, sizes={"posts": 90}))

        for record_type in RECORD_TYPES:
            assert f"{record_type}_rows" in payload
            assert f"{record_type}_bytes" in payload

    def test_zeroes_a_record_type_that_wrote_nothing(self):
        payload = get_flush_payload(summary(rows={"posts": 3}, sizes={"posts": 90}))

        assert payload["posts_rows"] == 3
        assert payload["likes_rows"] == 0
        assert payload["likes_bytes"] == 0

    def test_totals_across_record_types(self):
        payload = get_flush_payload(
            summary(rows={"posts": 3, "likes": 4}, sizes={"posts": 90, "likes": 120})
        )

        assert payload["total_rows"] == 7
        assert payload["total_bytes"] == 210

    def test_carries_the_reason(self):
        assert get_flush_payload(summary(reason=FLUSH_REASON_SIZE))["reason"] == FLUSH_REASON_SIZE

    def test_is_flat_so_logql_can_column_it(self):
        """`| json` gives one column per key only if no value is itself a structure."""

        payload = get_flush_payload(summary(rows={"posts": 3}, sizes={"posts": 90}))

        assert all(isinstance(value, str | int) for value in payload.values())


class TestRecordFlush:
    def test_logs_one_parseable_line_per_flush(self, caplog):
        with caplog.at_level("INFO"):
            record_flush(summary(rows={"reposts": 2}, sizes={"reposts": 64}))

        logged = [json.loads(m) for m in caplog.messages if m.startswith("{")]
        assert logged == [get_flush_payload(summary(rows={"reposts": 2}, sizes={"reposts": 64}))]

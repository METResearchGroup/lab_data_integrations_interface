import json

from bluesky_backfill_app.fetch_repos.constants import FLUSH_REASON_AGE, FLUSH_REASON_SIZE
from bluesky_backfill_app.fetch_repos.storage.buffer import FlushSummary
from bluesky_backfill_app.telemetry import instruments
from bluesky_backfill_app.telemetry.constants import FLUSH_STATUS_FAILED, FLUSH_STATUS_OK
from bluesky_backfill_app.telemetry.instruments import (
    get_flush_payload,
    record_flush,
    record_repo_failure,
)
from bluesky_ingestion_jetstream.constants import RECORD_TYPES


def summary(reason=FLUSH_REASON_AGE, repos=1, rows=None, sizes=None) -> FlushSummary:
    return FlushSummary(reason=reason, repos=repos, rows=rows or {}, sizes=sizes or {})


class FakeCounter:
    def __init__(self):
        self.adds = []

    def add(self, amount, attributes=None):
        self.adds.append((amount, attributes))


class TestFlushPayload:
    def test_every_record_type_appears_even_when_empty(self):
        payload = get_flush_payload(summary(rows={"posts": 3}, sizes={"posts": 90}), "ok")

        for record_type in RECORD_TYPES:
            assert f"{record_type}_rows" in payload
            assert f"{record_type}_mb" in payload

    def test_zeroes_a_record_type_that_wrote_nothing(self):
        payload = get_flush_payload(summary(rows={"posts": 3}, sizes={"posts": 90}), "ok")

        assert payload["posts_rows"] == 3
        assert payload["likes_rows"] == 0
        assert payload["likes_mb"] == 0

    def test_reports_megabytes_to_two_decimals(self):
        payload = get_flush_payload(summary(rows={"posts": 1}, sizes={"posts": 4_246_732}), "ok")

        assert payload["posts_mb"] == 4.25

    def test_totals_across_record_types(self):
        payload = get_flush_payload(
            summary(rows={"posts": 3, "likes": 4}, sizes={"posts": 1_500_000, "likes": 2_000_000}),
            "ok",
        )

        assert payload["total_rows"] == 7
        assert payload["total_mb"] == 3.5

    def test_carries_reason_status_and_repos(self):
        payload = get_flush_payload(
            summary(reason=FLUSH_REASON_SIZE, repos=12), FLUSH_STATUS_FAILED
        )

        assert payload["reason"] == FLUSH_REASON_SIZE
        assert payload["status"] == FLUSH_STATUS_FAILED
        assert payload["repos"] == 12

    def test_is_flat_so_logql_can_column_it(self):
        payload = get_flush_payload(summary(rows={"posts": 3}, sizes={"posts": 90}), "ok")

        assert all(isinstance(value, str | int | float) for value in payload.values())


class TestRecordFlush:
    def counters(self, monkeypatch):
        names = ("rows_written", "bytes_written", "repos_landed", "flush_failures")
        counters = {name: FakeCounter() for name in names}
        for name, counter in counters.items():
            monkeypatch.setattr(instruments, name, counter)
        return counters

    def test_logs_one_parseable_line_per_flush(self, caplog):
        flushed = summary(rows={"reposts": 2}, sizes={"reposts": 64})

        with caplog.at_level("INFO"):
            record_flush(flushed, FLUSH_STATUS_OK)

        logged = [json.loads(m) for m in caplog.messages if m.startswith("{")]
        assert logged == [get_flush_payload(flushed, FLUSH_STATUS_OK)]

    def test_counts_a_landed_flush(self, monkeypatch):
        counters = self.counters(monkeypatch)

        record_flush(summary(repos=5, rows={"likes": 7}, sizes={"likes": 300}), FLUSH_STATUS_OK)

        assert counters["rows_written"].adds == [(7, {"record_type": "likes"})]
        assert counters["bytes_written"].adds == [(300, {"record_type": "likes"})]
        assert counters["repos_landed"].adds == [(5, None)]
        assert counters["flush_failures"].adds == []

    def test_a_failed_flush_counts_only_as_a_failure(self, monkeypatch, caplog):
        counters = self.counters(monkeypatch)

        with caplog.at_level("INFO"):
            record_flush(summary(rows={"likes": 7}, sizes={"likes": 300}), FLUSH_STATUS_FAILED)

        assert counters.pop("flush_failures").adds == [(1, None)]
        assert all(counter.adds == [] for counter in counters.values())
        assert any('"status": "failed"' in m for m in caplog.messages)


def test_record_repo_failure_labels_reason_and_did_status(monkeypatch):
    counter = FakeCounter()
    monkeypatch.setattr(instruments, "repos_failed", counter)

    record_repo_failure("http_429", "queued")

    assert counter.adds == [(1, {"reason": "http_429", "did_status": "queued"})]

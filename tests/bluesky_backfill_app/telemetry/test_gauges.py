import pytest

from bluesky_backfill_app.aws.queue import Message
from bluesky_backfill_app.fetch_repos.storage.buffer import RepoBuffer
from bluesky_backfill_app.telemetry import gauges
from bluesky_backfill_app.telemetry.gauges import (
    observe_buffer_bytes,
    observe_in_flight_messages,
    observe_waiting_messages,
    register_buffer,
    register_queues,
)
from bluesky_ingestion_jetstream.constants import POSTS


class FakeQueue:
    def __init__(self, waiting=0, in_flight=0, error=None):
        self.waiting = waiting
        self.in_flight = in_flight
        self.error = error

    def waiting_messages(self):
        if self.error:
            raise self.error
        return self.waiting

    def in_flight_messages(self):
        if self.error:
            raise self.error
        return self.in_flight


@pytest.fixture(autouse=True)
def unregistered(monkeypatch):
    monkeypatch.setattr(gauges, "_buffer", None)
    monkeypatch.setattr(gauges, "_queues", {})


def values(observations):
    return [(o.value, dict(o.attributes or {})) for o in observations]


def test_buffer_reports_nothing_before_registration():
    assert list(observe_buffer_bytes(None)) == []


def test_buffer_reports_its_live_size():
    buffer = RepoBuffer()
    register_buffer(buffer)
    buffer.add(
        Message(did="did:plc:a", run_id="r", handle="h", receive_count=1),
        {POSTS: [{"uri": "at://did:plc:a/app.bsky.feed.post/1", "did": "did:plc:a"}]},
        0.0,
    )

    assert values(observe_buffer_bytes(None)) == [(buffer.size, {})]
    assert buffer.size > 0


def test_queues_report_nothing_before_registration():
    assert list(observe_waiting_messages(None)) == []


def test_each_queue_is_labelled_by_its_key():
    register_queues({"main": FakeQueue(1200), "dlq": FakeQueue(37)})

    assert values(observe_waiting_messages(None)) == [
        (1200, {"queue": "main"}),
        (37, {"queue": "dlq"}),
    ]


def test_a_failed_read_skips_only_that_queue():
    register_queues({"main": FakeQueue(error=RuntimeError("throttled")), "dlq": FakeQueue(37)})

    assert values(observe_waiting_messages(None)) == [(37, {"queue": "dlq"})]


def test_in_flight_reports_nothing_before_registration():
    assert list(observe_in_flight_messages(None)) == []


def test_in_flight_reads_only_the_main_queue():
    register_queues({"main": FakeQueue(in_flight=20_000), "dlq": FakeQueue(in_flight=5)})

    assert values(observe_in_flight_messages(None)) == [(20_000, {"queue": "main"})]


def test_a_failed_in_flight_read_reports_nothing():
    register_queues({"main": FakeQueue(error=RuntimeError("throttled"))})

    assert list(observe_in_flight_messages(None)) == []

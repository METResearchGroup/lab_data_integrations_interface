"""The heartbeat: values the reader pulls on every export, rather than ones we
push when something happens.

- `cursor.timestamp` -- stream position last written to DynamoDB, unix seconds.
- `connected` -- whether the Jetstream socket is up, 1 or 0.

Its own thread does the pulling, so these keep reporting even while the event
loop is blocked in a synchronous Iceberg commit.
"""

from collections.abc import Iterable

from opentelemetry import metrics
from opentelemetry.metrics import CallbackOptions, Observation

from bluesky_ingestion_jetstream.storage.cursor import CursorTracker
from bluesky_ingestion_jetstream.telemetry.constants import METER_NAME
from bluesky_ingestion_jetstream.telemetry.state import STREAM_STATE

MICROSECONDS_PER_SECOND = 1_000_000

meter = metrics.get_meter(METER_NAME)

# Set by `register_cursor_tracker`; until then the cursor gauge reports nothing.
_tracker: CursorTracker | None = None


def observe_cursor(_options: CallbackOptions) -> Iterable[Observation]:
    """The stored cursor as unix seconds. Grafana renders it as a date."""

    if _tracker is None or _tracker.cursor_value is None:
        return []
    return [Observation(_tracker.cursor_value / MICROSECONDS_PER_SECOND)]


def observe_connected(_options: CallbackOptions) -> Iterable[Observation]:
    """1 while the socket is up, 0 while it is not."""

    return [Observation(int(STREAM_STATE.connected))]


meter.create_observable_gauge(
    "bluesky_jetstream.cursor.timestamp",
    callbacks=[observe_cursor],
    unit="s",
    description="Stream position last written to DynamoDB, as unix seconds.",
)
meter.create_observable_gauge(
    "bluesky_jetstream.connected",
    callbacks=[observe_connected],
    unit="1",
    description="Whether the Jetstream socket is currently connected.",
)


def register_cursor_tracker(tracker: CursorTracker) -> None:
    """Point the cursor gauge at the live tracker. Called once, at startup."""

    global _tracker
    _tracker = tracker

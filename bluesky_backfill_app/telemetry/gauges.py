"""Gauges, read by the export thread every interval.

- `buffer.bytes` -- serialized JSON bytes buffered now.
- `queue.waiting_messages` by queue -- messages not yet received, main and DLQ.
- `queue.in_flight_messages` -- messages received but not yet acked, main only.

Every worker reports the whole queue, so aggregate the queue gauges with `max`.
"""

import logging
from collections.abc import Iterable

from opentelemetry import metrics
from opentelemetry.metrics import CallbackOptions, Observation

from bluesky_backfill_app.aws.queue import SqsQueue
from bluesky_backfill_app.fetch_repos.storage.buffer import RepoBuffer
from bluesky_backfill_app.telemetry.constants import METER_NAME, QUEUE_MAIN

logger = logging.getLogger(__name__)

QUEUE = "queue"

meter = metrics.get_meter(METER_NAME)

# Set at startup; until then the gauges report nothing.
_buffer: RepoBuffer | None = None
_queues: dict[str, SqsQueue] = {}


def observe_buffer_bytes(_options: CallbackOptions) -> Iterable[Observation]:
    if _buffer is None:
        return []
    return [Observation(_buffer.size)]


def observe_waiting_messages(_options: CallbackOptions) -> Iterable[Observation]:
    """A failed read skips that queue for this export rather than raising."""

    observations = []
    for name, queue in _queues.items():
        try:
            count = queue.waiting_messages()
        except Exception:
            logger.warning("could not read %s queue depth", name, exc_info=True)
            continue
        observations.append(Observation(count, {QUEUE: name}))
    return observations


def observe_in_flight_messages(_options: CallbackOptions) -> Iterable[Observation]:
    """Main queue only; nothing receives from the DLQ."""

    queue = _queues.get(QUEUE_MAIN)
    if queue is None:
        return []
    try:
        count = queue.in_flight_messages()
    except Exception:
        logger.warning("could not read %s in-flight count", QUEUE_MAIN, exc_info=True)
        return []
    return [Observation(count, {QUEUE: QUEUE_MAIN})]


meter.create_observable_gauge(
    "bluesky_backfill.buffer.bytes",
    callbacks=[observe_buffer_bytes],
    unit="By",
    description="Serialized JSON bytes buffered, awaiting flush.",
)
meter.create_observable_gauge(
    "bluesky_backfill.queue.waiting_messages",
    callbacks=[observe_waiting_messages],
    unit="{message}",
    description="Messages waiting to be received, by queue.",
)
meter.create_observable_gauge(
    "bluesky_backfill.queue.in_flight_messages",
    callbacks=[observe_in_flight_messages],
    unit="{message}",
    description="Messages received but not yet acked, main queue.",
)


def register_buffer(buffer: RepoBuffer) -> None:
    global _buffer
    _buffer = buffer


def register_queues(queues: dict[str, SqsQueue]) -> None:
    """`{"main": ..., "dlq": ...}`; the keys become the `queue` label."""

    global _queues
    _queues = queues

"""Live stream status, read by the gauges."""

from dataclasses import dataclass


@dataclass
class StreamState:
    """Whether the Jetstream socket is currently up."""

    connected: bool = False


STREAM_STATE = StreamState()

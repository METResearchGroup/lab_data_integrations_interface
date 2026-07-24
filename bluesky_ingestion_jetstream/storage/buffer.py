"""In-memory buffer holding events between disk writes."""


class Buffer:
    def add(self, event: dict) -> None:
        """Add an event to the buffer."""

        raise NotImplementedError

    def is_full(self) -> bool:
        """Whether the buffer has hit its flush threshold."""

        raise NotImplementedError

    def drain(self) -> list[dict]:
        """Return the buffered events and empty the buffer."""

        raise NotImplementedError

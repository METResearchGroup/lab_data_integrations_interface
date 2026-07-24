"""Entry point: stream from Jetstream, buffer, write to disk."""

from pathlib import Path


async def run(data_dir: Path) -> None:
    """Consume the stream, buffering events and writing them out when full."""
    print(data_dir)
    raise NotImplementedError


def main() -> None:
    """CLI entry point."""

    raise NotImplementedError


if __name__ == "__main__":
    main()

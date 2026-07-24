"""Write buffered events to disk."""

from pathlib import Path


def write(events: list[dict], data_dir: Path) -> Path:
    """Write events to a file under `data_dir` and return the path."""
    print(events)
    print(data_dir)
    raise NotImplementedError

"""Write buffered events to disk."""

from pathlib import Path


def write(record_type: str, rows: list[dict], data_dir: Path) -> Path:
    """Write rows to a file under `data_dir` and return the path."""
    print(record_type)
    print(rows)
    print(data_dir)
    raise NotImplementedError

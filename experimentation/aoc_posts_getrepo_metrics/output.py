"""Write metrics CSV and run metadata for the AOC getRepo experiment."""

from pathlib import Path


def write_outputs(rows: list[dict], metadata: dict, sync_timestamp: str) -> Path:
    """Write ``posts_metrics.csv`` and ``metadata.json`` under a run folder.

    Parameters
    ----------
    rows
        Metrics rows to serialize.
    metadata
        Run metadata written beside the CSV.
    sync_timestamp
        Timestamp folder name for this run.

    Returns
    -------
    Path
        Directory containing the written outputs.
    """
    raise NotImplementedError

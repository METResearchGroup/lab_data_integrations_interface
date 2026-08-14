"""Write metrics CSV and run metadata for the AOC getRepo experiment."""

import csv
import json
from pathlib import Path

from experimentation.aoc_posts_getrepo_metrics.constants import (
    CSV_FIELDNAMES,
    METADATA_FILENAME,
    METRICS_CSV_FILENAME,
    OUTPUT_ROOT,
)


def write_outputs(rows: list[dict], metadata: dict, sync_timestamp: str) -> Path:
    """Write ``posts_metrics.csv`` and ``metadata.json`` under a run folder.

    ``None`` values are written as empty CSV cells.

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

    Raises
    ------
    FileExistsError
        When ``sync_timestamp`` already exists under ``OUTPUT_ROOT``.
    """
    output_dir = OUTPUT_ROOT / sync_timestamp
    output_dir.mkdir(parents=True)

    csv_path = output_dir / METRICS_CSV_FILENAME
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES, restval="")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {key: ("" if row.get(key) is None else row.get(key)) for key in CSV_FIELDNAMES}
            )

    metadata_path = output_dir / METADATA_FILENAME
    with metadata_path.open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)

    return output_dir

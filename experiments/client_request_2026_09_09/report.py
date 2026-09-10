"""Stdout progress table for finished candidate exports."""

from __future__ import annotations

from dataclasses import dataclass

PROGRESS_COLUMN_PERSON = "Person"
PROGRESS_COLUMN_QUERY = "Query"
PROGRESS_COLUMN_TOTAL_RESULTS = "Total results"
PROGRESS_COLUMN_S3_PATH = "S3 path"
PROGRESS_TABLE_COLUMNS = (
    PROGRESS_COLUMN_PERSON,
    PROGRESS_COLUMN_QUERY,
    PROGRESS_COLUMN_TOTAL_RESULTS,
    PROGRESS_COLUMN_S3_PATH,
)
PROGRESS_TABLE_HEADER = "| " + " | ".join(PROGRESS_TABLE_COLUMNS) + " |"
PROGRESS_TABLE_SEPARATOR = "| " + " | ".join("---" for _ in PROGRESS_TABLE_COLUMNS) + " |"


@dataclass(frozen=True)
class ProgressRow:
    """One finished candidate row in the operator progress table."""

    person: str
    query: str
    total_results: int
    s3_path: str


def _collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


def _format_progress_data_row(row: ProgressRow) -> str:
    query_cell = _collapse_whitespace(row.query)
    cells = (row.person, query_cell, str(row.total_results), row.s3_path)
    return "| " + " | ".join(cells) + " |"


def format_progress_table(rows: list[ProgressRow]) -> str:
    """Format finished exports as a markdown table.

    The header line is exactly ``| Person | Query | Total results | S3 path |``.
    Query cells collapse SQL whitespace to single spaces. Callers reprint the
    full table after each finished candidate.

    Parameters
    ----------
    rows
        Finished candidates in the order they completed.

    Returns
    -------
    str
        Markdown table including the header, separator, and one data row each.
    """

    lines = [PROGRESS_TABLE_HEADER, PROGRESS_TABLE_SEPARATOR]
    lines.extend(_format_progress_data_row(row) for row in rows)
    return "\n".join(lines)

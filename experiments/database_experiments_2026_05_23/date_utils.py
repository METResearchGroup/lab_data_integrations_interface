"""Timestamp parsing and range helpers for string-formatted created_at values.

Run from repo root:
    PYTHONPATH=. uv run python -c "from experiments.database_experiments_2026_05_23.date_utils import days_ago; print(days_ago(7))"
"""

from datetime import UTC, datetime, timedelta

from lib.timestamp_utils import CREATED_AT_FORMAT


def parse_created_at(value: str) -> datetime:
    return datetime.strptime(value, CREATED_AT_FORMAT).replace(tzinfo=UTC)


def format_created_at(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime(CREATED_AT_FORMAT)


def start_of_today() -> datetime:
    now = datetime.now(UTC)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def days_ago(n: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=n)


def format_range_start(dt: datetime) -> str:
    """Format a datetime as a string lower bound for created_at comparisons."""
    return format_created_at(dt)


def date_only_key(created_at: str) -> str:
    """Extract YYYY_MM_DD prefix from a created_at string."""
    return created_at[:10]

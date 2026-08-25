"""Turns a validated QueryIntent into Athena SQL."""

from __future__ import annotations

from datetime import date, timedelta

from backend.agentic_search.query_generation.models import GeneratedQuery
from backend.agentic_search.query_validation.query_intent.models import QueryIntent
from bluesky_ingestion_jetstream.aws.constants import GLUE_DATABASE, PARTITION_SOURCE_COLUMN

DEFAULT_LIMIT = 1000


def _quote(identifier: str) -> str:
    return '"{}"'.format(identifier.replace('"', '""'))


def _select_clause(columns: list[str]) -> str:
    selection = ", ".join(_quote(column) for column in columns) if columns else "*"
    return f"SELECT {selection}"


def _from_clause(table: str) -> str:
    return f"FROM {table}"


def _timestamp(day: date) -> str:
    return f"TIMESTAMP '{day} 00:00:00'"


def _where_clause(start_date: date | None, end_date: date | None) -> str:
    conditions = []
    if start_date is not None:
        conditions.append(f"{PARTITION_SOURCE_COLUMN} >= {_timestamp(start_date)}")
    if end_date is not None:
        conditions.append(f"{PARTITION_SOURCE_COLUMN} < {_timestamp(end_date + timedelta(days=1))}")

    return f"WHERE {' AND '.join(conditions)}" if conditions else ""


def _order_by_clause() -> str:
    return f"ORDER BY {PARTITION_SOURCE_COLUMN}"


def _limit_clause(limit: int) -> str:
    return f"LIMIT {limit}"


def generate_sql(intent: QueryIntent, *, limit: int = DEFAULT_LIMIT) -> GeneratedQuery:
    """Assumes the intent already passed validation."""

    if intent.record_type is None:
        raise ValueError("intent has no record type")

    table = f"{GLUE_DATABASE}.{intent.record_type.value}"
    clauses = [
        _select_clause(intent.columns),
        _from_clause(table),
        _where_clause(intent.start_date, intent.end_date),
        _order_by_clause(),
        _limit_clause(limit),
    ]

    return GeneratedQuery(
        sql="\n".join(clause for clause in clauses if clause),
        record_type=intent.record_type,
    )

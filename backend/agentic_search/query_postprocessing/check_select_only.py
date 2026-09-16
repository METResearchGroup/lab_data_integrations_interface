"""Rejects anything but a single read-only query."""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError


def is_select_only(sql: str) -> bool:
    """SQL that does not parse fails closed."""

    try:
        statements = sqlglot.parse(sql, dialect="athena")
    except SqlglotError:
        return False

    # `Query` is SELECT, WITH ... SELECT, and set operations like UNION.
    return len(statements) == 1 and isinstance(statements[0], exp.Query)

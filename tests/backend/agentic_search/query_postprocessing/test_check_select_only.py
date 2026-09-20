"""Everything that is not one read-only statement has to be refused."""

from __future__ import annotations

from datetime import date

import pytest

from backend.agentic_search.query_generation.generate import generate_sql
from backend.agentic_search.query_postprocessing.check_select_only import is_select_only
from backend.agentic_search.query_validation.query_intent.models import QueryIntent
from bluesky_ingestion_jetstream.constants import RecordType


def test_generated_sql_passes() -> None:
    """The real generator's output, so the check cannot drift away from it."""

    generated = generate_sql(
        QueryIntent(
            is_nonsense=False,
            record_type=RecordType.POSTS,
            columns=["text", "langs"],
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
        )
    )

    assert is_select_only(generated.sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "SELECT * FROM posts WHERE created_at > TIMESTAMP '2026-07-01 00:00:00'",
        "WITH recent AS (SELECT * FROM posts) SELECT text FROM recent",
        "SELECT 1 UNION ALL SELECT 2",
    ],
)
def test_reads_pass(sql: str) -> None:
    assert is_select_only(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM posts",
        "UPDATE posts SET text = 'x'",
        "INSERT INTO posts SELECT * FROM posts",
        "DROP TABLE posts",
        "CREATE TABLE t AS SELECT 1",
        "MERGE INTO posts USING other ON posts.uri = other.uri WHEN MATCHED THEN DELETE",
        "OPTIMIZE posts REWRITE DATA USING BIN_PACK",
        "VACUUM posts",
        "UNLOAD (SELECT 1) TO 's3://bucket/x/' WITH (format = 'PARQUET')",
        # Stacked statements: the write rides along behind a legitimate read.
        "SELECT 1; DROP TABLE posts",
        # Neither parses, so neither can be shown to be a read.
        "SELEC 1",
        "",
    ],
)
def test_writes_and_junk_fail(sql: str) -> None:
    assert not is_select_only(sql)

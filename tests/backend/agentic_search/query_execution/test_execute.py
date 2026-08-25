"""execute_query wiring, against stubbed Athena and S3 clients."""

from __future__ import annotations

from typing import Any

import pytest

from backend.agentic_search.query_execution.execute import WORKGROUP, execute_query
from backend.agentic_search.query_generation.models import GeneratedQuery
from bluesky_ingestion_jetstream.aws.constants import GLUE_DATABASE
from bluesky_ingestion_jetstream.constants import RecordType

GENERATED = GeneratedQuery(
    sql='SELECT "text"\nFROM bluesky_raw.posts\nLIMIT 1000',
    record_type=RecordType.POSTS,
)

OUTPUT_LOCATION = "s3://aws-athena-query-results-us-east-2/execution-1.csv"


class StubAthena:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run_query(self, query: str, *, database: str, workgroup: str) -> str:
        self.calls.append({"query": query, "database": database, "workgroup": workgroup})
        return "execution-1"

    def get_output_location(self, _execution_id: str) -> str:
        return OUTPUT_LOCATION


class StubS3:
    def __init__(self) -> None:
        self.presigned: list[tuple[str, int]] = []

    def generate_presigned_url(self, s3_uri: str, expires_in: int = 86_400) -> str:
        self.presigned.append((s3_uri, expires_in))
        return f"https://signed/{s3_uri}"


@pytest.fixture
def stubs() -> tuple[StubAthena, StubS3]:
    return StubAthena(), StubS3()


def test_submits_the_sql_unwrapped(stubs) -> None:
    athena, s3 = stubs
    execute_query(GENERATED, athena=athena, s3=s3)

    # Athena's own result file is the deliverable, so there is nothing to wrap.
    assert athena.calls[0]["query"] == GENERATED.sql
    assert athena.calls[0]["database"] == GLUE_DATABASE
    assert athena.calls[0]["workgroup"] == WORKGROUP


def test_presigns_the_result_file(stubs) -> None:
    athena, s3 = stubs
    result = execute_query(GENERATED, athena=athena, s3=s3, expires_in=60)

    assert result.execution_id == "execution-1"
    assert result.result_url == f"https://signed/{OUTPUT_LOCATION}"
    assert s3.presigned == [(OUTPUT_LOCATION, 60)]


def test_default_ttl_is_a_day(stubs) -> None:
    athena, s3 = stubs
    execute_query(GENERATED, athena=athena, s3=s3)

    assert s3.presigned[0][1] == 86_400

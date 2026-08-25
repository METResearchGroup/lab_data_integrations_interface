"""Runs a generated query through Athena and presigns its CSV result."""

from __future__ import annotations

from backend.agentic_search.query_execution.models import ExecutedQuery
from backend.agentic_search.query_generation.models import GeneratedQuery
from bluesky_ingestion_jetstream.aws.constants import GLUE_DATABASE
from data_platform.aws.athena import Athena
from data_platform.aws.s3 import S3

# The only workgroup terraform/bluesky_ingestion_jetstream creates.
WORKGROUP = "bluesky_raw_maintenance"

PRESIGNED_URL_TTL_SECONDS = 86_400


def execute_query(
    generated: GeneratedQuery,
    *,
    athena: Athena | None = None,
    s3: S3 | None = None,
    expires_in: int = PRESIGNED_URL_TTL_SECONDS,
) -> ExecutedQuery:
    """Run the query and presign the result file Athena writes for it."""

    athena = athena or Athena()
    s3 = s3 or S3()

    execution_id = athena.run_query(
        generated.sql,
        database=GLUE_DATABASE,
        workgroup=WORKGROUP,
    )

    return ExecutedQuery(
        execution_id=execution_id,
        result_url=s3.generate_presigned_url(
            athena.get_output_location(execution_id),
            expires_in=expires_in,
        ),
    )

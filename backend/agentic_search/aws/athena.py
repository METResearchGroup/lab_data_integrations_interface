"""The slice of Athena that running a search query needs."""

from __future__ import annotations

import time

import boto3

from bluesky_ingestion_jetstream.aws.constants import AWS_REGION

POLL_INTERVAL_SECONDS = 1.0


class Athena:
    def __init__(self, region: str = AWS_REGION) -> None:
        self.client = boto3.client("athena", region_name=region)

    def run_query(self, query: str, *, database: str, workgroup: str) -> str:
        """Submit a query and poll until it finishes. Returns the execution ID."""

        execution_id = self.client.start_query_execution(
            QueryString=query,
            QueryExecutionContext={"Database": database},
            WorkGroup=workgroup,
        )["QueryExecutionId"]

        while True:
            status = self.client.get_query_execution(QueryExecutionId=execution_id)[
                "QueryExecution"
            ]["Status"]
            state = status["State"]
            if state == "SUCCEEDED":
                return execution_id
            if state in ("FAILED", "CANCELLED"):
                raise RuntimeError(
                    f"Athena query {state}: {status.get('StateChangeReason', 'unknown')}"
                )
            time.sleep(POLL_INTERVAL_SECONDS)

    def get_output_location(self, execution_id: str) -> str:
        """The s3:// URI of the result CSV Athena wrote for a finished query."""

        response = self.client.get_query_execution(QueryExecutionId=execution_id)
        return response["QueryExecution"]["ResultConfiguration"]["OutputLocation"]

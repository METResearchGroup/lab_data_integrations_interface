"""Shared Athena helper for running a query and locating its result file."""

from __future__ import annotations

import time

from lib.aws.clients import build_athena_client
from lib.aws.constants import AWS_REGION

POLL_INTERVAL_SECONDS = 1.0


class Athena:
    """Submits an Athena query, waits for it to finish, and locates the result CSV."""

    def __init__(self, region: str = AWS_REGION, client=None) -> None:
        self.client = client if client is not None else build_athena_client(region, None)

    def run_query(self, query: str, database: str, workgroup: str) -> str:
        """Submit a query and poll until it finishes.

        Returns
        -------
        str
            The Athena query execution id.

        Raises
        ------
        RuntimeError
            If Athena reports FAILED or CANCELLED.
        """

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
        """Return the s3:// URI of the result CSV Athena wrote for a finished query."""

        response = self.client.get_query_execution(QueryExecutionId=execution_id)
        return response["QueryExecution"]["ResultConfiguration"]["OutputLocation"]

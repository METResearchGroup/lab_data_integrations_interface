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
        """Submit a query and poll until it finishes. Return the execution id."""

        raise NotImplementedError

    def get_output_location(self, execution_id: str) -> str:
        """Return the s3:// URI of the result CSV Athena wrote for a finished query."""

        raise NotImplementedError

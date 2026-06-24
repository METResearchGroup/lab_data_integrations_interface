from __future__ import annotations

import time

import boto3

from data_platform.aws.constants import DEFAULT_DATABASE, DEFAULT_REGION, DEFAULT_WORKGROUP


class Athena:
    def __init__(self, region: str = DEFAULT_REGION) -> None:
        self.client = boto3.client("athena", region_name=region)

    def run_query(
        self, query: str, *, database: str = DEFAULT_DATABASE, workgroup: str = DEFAULT_WORKGROUP
    ) -> str:
        """Submit a query and poll until it completes. Returns the execution ID."""
        response = self.client.start_query_execution(
            QueryString=query,
            QueryExecutionContext={"Database": database},
            WorkGroup=workgroup,
        )
        execution_id = response["QueryExecutionId"]
        while True:
            state = self.client.get_query_execution(QueryExecutionId=execution_id)
            status = state["QueryExecution"]["Status"]["State"]
            if status == "SUCCEEDED":
                return execution_id
            if status in ("FAILED", "CANCELLED"):
                reason = state["QueryExecution"]["Status"].get("StateChangeReason", "unknown")
                raise RuntimeError(f"Athena query {status}: {reason}")
            time.sleep(1)

    def fetch_column_as_set(self, execution_id: str, *, column_index: int = 0) -> set[str]:
        """Paginate results and return unique non-empty string values from one column."""
        seen: set[str] = set()
        paginator = self.client.get_paginator("get_query_results")
        first_page = True
        for page in paginator.paginate(QueryExecutionId=execution_id):
            rows = page["ResultSet"]["Rows"]
            for row in rows[1:] if first_page else rows:
                value = row["Data"][column_index].get("VarCharValue")
                if value:
                    seen.add(value)
            first_page = False
        return seen

    def query_column_as_set(
        self,
        query: str,
        *,
        database: str = DEFAULT_DATABASE,
        workgroup: str = DEFAULT_WORKGROUP,
        column_index: int = 0,
    ) -> set[str]:
        """Run a query and return one column as a set of strings."""
        execution_id = self.run_query(query, database=database, workgroup=workgroup)
        return self.fetch_column_as_set(execution_id, column_index=column_index)

    def register_partition(
        self,
        table: str,
        partition_values: dict[str, str],
        s3_location: str,
    ) -> None:
        """Register a new partition with Glue via ALTER TABLE ADD IF NOT EXISTS PARTITION."""
        pairs = ", ".join(f"{k}='{v}'" for k, v in partition_values.items())
        self.run_query(
            f"ALTER TABLE {table} ADD IF NOT EXISTS PARTITION ({pairs}) LOCATION '{s3_location}'"
        )

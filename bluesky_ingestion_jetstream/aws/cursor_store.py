"""The resume cursor, stored as a single DynamoDB item."""

import logging
from datetime import UTC, datetime

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from bluesky_ingestion_jetstream.aws.constants import (
    AWS_REGION,
    CURSOR_ATTRIBUTE,
    CURSOR_PARTITION_KEY,
    CURSOR_STREAM_ID,
    CURSOR_TABLE,
    DYNAMODB_CONNECT_TIMEOUT_SECONDS,
    DYNAMODB_MAX_ATTEMPTS,
    DYNAMODB_READ_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)

CONDITIONAL_CHECK_FAILED = "ConditionalCheckFailedException"


def error_code(error: ClientError) -> str:
    return error.response.get("Error", {}).get("Code", "")


def build_dynamodb_client():
    return boto3.client(
        "dynamodb",
        region_name=AWS_REGION,
        config=Config(
            retries={"max_attempts": DYNAMODB_MAX_ATTEMPTS, "mode": "standard"},
            connect_timeout=DYNAMODB_CONNECT_TIMEOUT_SECONDS,
            read_timeout=DYNAMODB_READ_TIMEOUT_SECONDS,
        ),
    )


class DynamoCursorStore:
    """Reads the cursor once at startup and rewrites it after every flush."""

    def __init__(
        self,
        client=None,
        table: str = CURSOR_TABLE,
        stream_id: str = CURSOR_STREAM_ID,
    ) -> None:
        self.client = client if client is not None else build_dynamodb_client()
        self.table = table
        self.stream_id = stream_id

    @property
    def key(self) -> dict:
        return {CURSOR_PARTITION_KEY: {"S": self.stream_id}}

    def read(self) -> int | None:
        """Load the stored cursor, raising rather than silently starting live.

        No item is a cold start and returns None; a failed read is not, and
        treating the two alike would skip everything since the last run. The
        client's own retries cover a blip; past those, exiting is the recovery.
        """

        response = self.client.get_item(TableName=self.table, Key=self.key, ConsistentRead=True)
        item = response.get("Item")
        if not item:
            return None
        return int(item[CURSOR_ATTRIBUTE]["N"])

    def write(self, time_us: int) -> None:
        """Store `time_us`, conditioned so the cursor cannot move backwards."""

        try:
            self.client.update_item(
                TableName=self.table,
                Key=self.key,
                UpdateExpression=f"SET {CURSOR_ATTRIBUTE} = :cursor, updated_at = :updated_at",
                ConditionExpression=(
                    f"attribute_not_exists({CURSOR_ATTRIBUTE}) OR {CURSOR_ATTRIBUTE} < :cursor"
                ),
                ExpressionAttributeValues={
                    ":cursor": {"N": str(time_us)},
                    ":updated_at": {"S": datetime.now(UTC).isoformat()},
                },
            )
        except ClientError as error:
            if error_code(error) != CONDITIONAL_CHECK_FAILED:
                raise
            # A guard against a stale writer, not a lock: single writer is assumed.
            logger.warning("stored cursor is already ahead of %d; leaving it", time_us)

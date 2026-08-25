import logging
from datetime import UTC, datetime

from bluesky_backfill_app.aws.clients import build_dynamodb_client
from bluesky_backfill_app.aws.constants import (
    CURSOR_ATTRIBUTE,
    CURSOR_PARTITION_KEY,
    CURSOR_RUN_ID,
    CURSOR_TABLE,
    DISCOVERED_COUNT_ATTRIBUTE,
    UPDATED_AT_ATTRIBUTE,
)

logger = logging.getLogger(__name__)


class DynamoCursorStore:
    """The listRepos cursor and running DID count, as a single item."""

    def __init__(
        self,
        client=None,
        table: str = CURSOR_TABLE,
        run_id: str = CURSOR_RUN_ID,
    ) -> None:
        self.client = client if client is not None else build_dynamodb_client()
        self.table = table
        self.run_id = run_id

    @property
    def key(self) -> dict:
        return {CURSOR_PARTITION_KEY: {"S": self.run_id}}

    def read(self) -> tuple[str | None, int]:
        """Stored cursor and count, or `(None, 0)` on a fresh run."""

        response = self.client.get_item(TableName=self.table, Key=self.key, ConsistentRead=True)
        item = response.get("Item")
        if not item:
            return None, 0
        return (
            item.get(CURSOR_ATTRIBUTE, {}).get("S"),
            int(item.get(DISCOVERED_COUNT_ATTRIBUTE, {}).get("N", 0)),
        )

    def write(self, cursor: str, created_count: int) -> None:
        """Set the cursor and ADD `created_count`, in one UpdateItem."""

        self.client.update_item(
            TableName=self.table,
            Key=self.key,
            UpdateExpression=(
                f"SET {CURSOR_ATTRIBUTE} = :cursor, {UPDATED_AT_ATTRIBUTE} = :updated_at "
                f"ADD {DISCOVERED_COUNT_ATTRIBUTE} :created"
            ),
            ExpressionAttributeValues={
                ":cursor": {"S": cursor},
                ":created": {"N": str(created_count)},
                ":updated_at": {"S": datetime.now(UTC).isoformat()},
            },
        )

import logging

from bluesky_backfill_app.aws.constants import UPDATED_AT_ATTRIBUTE
from bluesky_backfill_app.gather_users.constants import (
    CURSOR_ATTRIBUTE,
    CURSOR_PARTITION_KEY,
    CURSOR_RUN_ID,
    CURSOR_TABLE,
)
from lib.aws.constants import AWS_REGION
from lib.aws.dynamodb import DynamoDB
from lib.timestamp_utils import get_current_timestamp

logger = logging.getLogger(__name__)


class DynamoCursorStore(DynamoDB):
    """The listRepos cursor, as a single item."""

    def __init__(
        self,
        client=None,
        table: str = CURSOR_TABLE,
        run_id: str = CURSOR_RUN_ID,
    ) -> None:
        super().__init__(table=table, client=client, region=AWS_REGION, config=None)
        self.run_id = run_id

    @property
    def key(self) -> dict:
        return {CURSOR_PARTITION_KEY: {"S": self.run_id}}

    def read(self) -> str | None:
        """Stored cursor, or None on a fresh run."""

        response = self.client.get_item(TableName=self.table, Key=self.key, ConsistentRead=True)
        return response.get("Item", {}).get(CURSOR_ATTRIBUTE, {}).get("S")

    def write(self, cursor: str) -> None:
        self.client.update_item(
            TableName=self.table,
            Key=self.key,
            UpdateExpression=(
                f"SET {CURSOR_ATTRIBUTE} = :cursor, {UPDATED_AT_ATTRIBUTE} = :updated_at"
            ),
            ExpressionAttributeValues={
                ":cursor": {"S": cursor},
                ":updated_at": {"S": get_current_timestamp()},
            },
        )

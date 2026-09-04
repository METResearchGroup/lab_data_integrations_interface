"""DynamoDB store for backfill DIDs and their status lifecycle."""

import logging
from concurrent.futures import ThreadPoolExecutor
from zlib import crc32

from botocore.exceptions import ClientError

from bluesky_backfill_app.aws.constants import (
    DID_PARTITION_KEY,
    DID_TABLE,
    DISCOVERED_AT_ATTRIBUTE,
    RUN_ID_ATTRIBUTE,
    STATUS_ATTRIBUTE,
    STATUS_DISCOVERED,
    STATUS_INDEX,
    STATUS_SHARD_ATTRIBUTE,
    STATUS_SHARD_COUNT,
    UPDATED_AT_ATTRIBUTE,
    WRITE_CONCURRENCY,
)
from lib.aws.clients import CONDITIONAL_CHECK_FAILED, error_code
from lib.aws.constants import AWS_REGION
from lib.aws.dynamodb import DynamoDBStore
from lib.timestamp_utils import get_current_timestamp

logger = logging.getLogger(__name__)


def shard_key(status: str, shard: int) -> str:
    return f"{status}#{shard}"


def status_shard(did: str, status: str) -> str:
    """GSI partition key: `{status}#{shard}`."""

    # crc32, not hash(): str hashing is salted per process.
    return shard_key(status, crc32(did.encode()) % STATUS_SHARD_COUNT)


class DynamoDidStore(DynamoDBStore):
    def __init__(
        self,
        client=None,
        table: str = DID_TABLE,
        concurrency: int = WRITE_CONCURRENCY,
    ) -> None:
        super().__init__(table=table, client=client, region=AWS_REGION, config=None)
        self.concurrency = concurrency

    def put_new(self, did: str, run_id: str) -> bool:
        """Conditional PutItem at STATUS_DISCOVERED. False if the DID already exists."""

        now = get_current_timestamp()
        try:
            self.client.put_item(
                TableName=self.table,
                Item={
                    DID_PARTITION_KEY: {"S": did},
                    STATUS_ATTRIBUTE: {"S": STATUS_DISCOVERED},
                    STATUS_SHARD_ATTRIBUTE: {"S": status_shard(did, STATUS_DISCOVERED)},
                    DISCOVERED_AT_ATTRIBUTE: {"S": now},
                    UPDATED_AT_ATTRIBUTE: {"S": now},
                    RUN_ID_ATTRIBUTE: {"S": run_id},
                },
                ConditionExpression=f"attribute_not_exists({DID_PARTITION_KEY})",
            )
        except ClientError as error:
            if error_code(error) == CONDITIONAL_CHECK_FAILED:
                return False
            raise
        return True

    def write(self, dids: list[str], run_id: str) -> int:
        """Put `dids` concurrently, returning how many were newly created.

        Raises if any DID fails for a reason other than already existing.
        """

        if not dids:
            return 0

        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            created = list(pool.map(lambda did: self.put_new(did, run_id), dids))
        return sum(created)

    def set_status(self, did: str, status: str) -> None:
        """Rewrite `status` and its shard key together."""

        self.client.update_item(
            TableName=self.table,
            Key={DID_PARTITION_KEY: {"S": did}},
            UpdateExpression=(
                f"SET #status = :status, {STATUS_SHARD_ATTRIBUTE} = :shard, "
                f"{UPDATED_AT_ATTRIBUTE} = :updated_at"
            ),
            # `status` is a DynamoDB reserved word.
            ExpressionAttributeNames={"#status": STATUS_ATTRIBUTE},
            ExpressionAttributeValues={
                ":status": {"S": status},
                ":shard": {"S": status_shard(did, status)},
                ":updated_at": {"S": get_current_timestamp()},
            },
            ConditionExpression=f"attribute_exists({DID_PARTITION_KEY})",
        )

    def set_status_many(self, dids: list[str], status: str) -> None:
        """Advance `dids` concurrently. Raises if any one fails."""

        if not dids:
            return

        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            list(pool.map(lambda did: self.set_status(did, status), dids))

    def query_by_status(self, status: str, limit: int) -> list[str]:
        dids: list[str] = []

        for shard in range(STATUS_SHARD_COUNT):
            remaining = limit - len(dids)
            if remaining <= 0:
                break
            response = self.client.query(
                TableName=self.table,
                IndexName=STATUS_INDEX,
                KeyConditionExpression=f"{STATUS_SHARD_ATTRIBUTE} = :shard",
                ExpressionAttributeValues={":shard": {"S": shard_key(status, shard)}},
                Limit=remaining,
            )
            dids.extend(item[DID_PARTITION_KEY]["S"] for item in response.get("Items", []))

        return dids

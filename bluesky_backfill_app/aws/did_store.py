import logging

from bluesky_backfill_app.aws.clients import build_dynamodb_client
from bluesky_backfill_app.aws.constants import DID_TABLE, WRITE_CONCURRENCY

logger = logging.getLogger(__name__)


def status_shard(did: str, status: str) -> str:
    """GSI partition key: `{status}#{shard}`."""

    raise NotImplementedError


class DynamoDidStore:
    def __init__(
        self,
        client=None,
        table: str = DID_TABLE,
        concurrency: int = WRITE_CONCURRENCY,
    ) -> None:
        self.client = client if client is not None else build_dynamodb_client()
        self.table = table
        self.concurrency = concurrency

    def put_new(self, did: str, run_id: str) -> bool:
        """Conditional PutItem at STATUS_DISCOVERED. False if the DID already exists."""

        raise NotImplementedError

    def write(self, dids: list[str], run_id: str) -> int:
        """Put `dids` concurrently, returning how many were newly created.

        Raises if any DID fails for a reason other than already existing.
        """

        raise NotImplementedError

    def set_status(self, did: str, status: str) -> None:
        """Rewrite `status` and its shard key together."""

        raise NotImplementedError

    def query_by_status(self, status: str, limit: int) -> list[str]:
        raise NotImplementedError

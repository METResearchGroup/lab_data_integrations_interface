import logging

from bluesky_backfill_app.aws.clients import build_dynamodb_client
from bluesky_backfill_app.aws.constants import CURSOR_RUN_ID, CURSOR_TABLE

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
        raise NotImplementedError

    def read(self) -> tuple[str | None, int]:
        """Stored cursor and count, or `(None, 0)` on a fresh run."""

        raise NotImplementedError

    def write(self, cursor: str, created_count: int) -> None:
        """Set the cursor and ADD `created_count`, in one UpdateItem."""

        raise NotImplementedError

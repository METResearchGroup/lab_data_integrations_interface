"""Send discovered DIDs to the SQS queue the fetch workers read from."""

import json
import logging

from bluesky_backfill_app.aws.constants import QUEUE_NAME
from lib.aws.constants import AWS_REGION
from lib.aws.sqs import SQS_BATCH_SIZE, SqsQueueBase

logger = logging.getLogger(__name__)


def message_body(did: str, run_id: str) -> str:
    return json.dumps({"did": did, "run_id": run_id})


def chunked(dids: list[str], size: int) -> list[list[str]]:
    return [dids[start : start + size] for start in range(0, len(dids), size)]


class SqsQueue(SqsQueueBase):
    """Publishes DIDs to the queue."""

    def __init__(self, client=None, queue_url: str | None = None, queue_name: str = QUEUE_NAME):
        super().__init__(
            client=client, queue_url=queue_url, queue_name=queue_name, region=AWS_REGION
        )

    def send_batch(self, dids: list[str], run_id: str) -> list[str]:
        """Send one batch of at most SQS_BATCH_SIZE DIDs. Returns those that failed."""

        entries = [
            {"Id": str(index), "MessageBody": message_body(did, run_id)}
            for index, did in enumerate(dids)
        ]
        response = self.send_message_batch(entries)

        failed_ids = {entry["Id"] for entry in response.get("Failed", [])}
        return [did for index, did in enumerate(dids) if str(index) in failed_ids]

    def send(self, dids: list[str], run_id: str) -> list[str]:
        """Send `dids` in batches. Returns every DID that failed."""

        failed: list[str] = []
        for chunk in chunked(dids, SQS_BATCH_SIZE):
            failed.extend(self.send_batch(chunk, run_id))

        if failed:
            logger.warning("%d of %d dids failed to send", len(failed), len(dids))
        return failed

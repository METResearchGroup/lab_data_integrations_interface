"""Shared SQS helper that owns a client, queue URL, and queue name."""

from __future__ import annotations

from lib.aws.clients import build_sqs_client
from lib.aws.constants import AWS_REGION

SQS_BATCH_SIZE = 10


class SQS:
    """Holds an SQS client, queue URL, and queue name for a subclass to use."""

    def __init__(
        self,
        queue_url: str,
        queue_name: str,
        client=None,
        region: str = AWS_REGION,
    ) -> None:
        self.client = client if client is not None else build_sqs_client(region, None)
        self.queue_url = queue_url
        self.queue_name = queue_name

    def send_message_batch(self, entries: list[dict]) -> dict:
        """Send one SendMessageBatch request and return the client response."""

        return self.client.send_message_batch(QueueUrl=self.queue_url, Entries=entries)

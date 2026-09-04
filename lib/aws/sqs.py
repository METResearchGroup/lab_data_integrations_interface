"""Shared SQS helper that owns a client and a queue URL."""

from __future__ import annotations

from lib.aws.clients import build_sqs_client
from lib.aws.constants import AWS_REGION

SQS_BATCH_SIZE = 10


class SqsQueueBase:
    """Holds an SQS client and queue URL for a subclass to use."""

    def __init__(
        self,
        client=None,
        queue_url: str | None = None,
        queue_name: str | None = None,
        region: str = AWS_REGION,
    ) -> None:
        self.client = client if client is not None else build_sqs_client(region, None)
        if queue_url is None and queue_name is None:
            raise ValueError("pass queue_url or queue_name")
        self.queue_url = queue_url or self.client.get_queue_url(QueueName=queue_name)["QueueUrl"]

    def send_message_batch(self, entries: list[dict]) -> dict:
        """Send one SendMessageBatch request and return the client response."""

        raise NotImplementedError

"""Send DIDs to the SQS queue and receive them in the fetch workers."""

import json
import logging
from dataclasses import dataclass
from typing import Any

from bluesky_backfill_app.aws.constants import (
    IN_FLIGHT_MESSAGES_ATTRIBUTE,
    MAX_RECEIVE_COUNT,
    QUEUE_NAME,
    RECEIVE_COUNT_ATTRIBUTE,
    RECEIVE_WAIT_SECONDS,
    WAITING_MESSAGES_ATTRIBUTE,
)
from lib.aws.clients import build_sqs_client
from lib.aws.constants import AWS_REGION
from lib.aws.sqs import SQS, SQS_BATCH_SIZE

logger = logging.getLogger(__name__)


def message_body(did: str, run_id: str) -> str:
    return json.dumps({"did": did, "run_id": run_id})


def chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[start : start + size] for start in range(0, len(items), size)]


@dataclass(frozen=True, slots=True)
class Message:
    did: str
    run_id: str
    handle: str
    receive_count: int

    @property
    def is_final_delivery(self) -> bool:
        """True if SQS dead-letters this message instead of redelivering it."""

        return self.receive_count >= MAX_RECEIVE_COUNT


def parse_message(message: dict[str, Any]) -> Message:
    body = json.loads(message["Body"])
    attributes = message.get("Attributes", {})
    return Message(
        did=body["did"],
        run_id=body["run_id"],
        handle=message["ReceiptHandle"],
        receive_count=int(attributes.get(RECEIVE_COUNT_ATTRIBUTE, 1)),
    )


class SqsQueue(SQS):
    """Sends and receives DIDs."""

    def __init__(self, client=None, queue_url: str | None = None, queue_name: str = QUEUE_NAME):
        client = client if client is not None else build_sqs_client(AWS_REGION, None)
        resolved_url = queue_url or client.get_queue_url(QueueName=queue_name)["QueueUrl"]
        super().__init__(
            queue_url=resolved_url,
            queue_name=queue_name,
            client=client,
            region=AWS_REGION,
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

    def receive(self, wait_seconds: int = RECEIVE_WAIT_SECONDS) -> Message | None:
        """Long-poll for one message. None if the queue is empty."""

        response = self.client.receive_message(
            QueueUrl=self.queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=wait_seconds,
            MessageSystemAttributeNames=[RECEIVE_COUNT_ATTRIBUTE],
        )

        messages = response.get("Messages", [])
        return parse_message(messages[0]) if messages else None

    def waiting_messages(self) -> int:
        """Approximate count of messages not yet received."""

        response = self.client.get_queue_attributes(
            QueueUrl=self.queue_url,
            AttributeNames=[WAITING_MESSAGES_ATTRIBUTE],
        )
        return int(response["Attributes"][WAITING_MESSAGES_ATTRIBUTE])

    def in_flight_messages(self) -> int:
        """Approximate count of messages received but not yet deleted."""

        response = self.client.get_queue_attributes(
            QueueUrl=self.queue_url,
            AttributeNames=[IN_FLIGHT_MESSAGES_ATTRIBUTE],
        )
        return int(response["Attributes"][IN_FLIGHT_MESSAGES_ATTRIBUTE])

    def delete(self, handle: str) -> None:
        """Ack one message."""

        self.client.delete_message(QueueUrl=self.queue_url, ReceiptHandle=handle)

    def delete_batch(self, handles: list[str]) -> list[str]:
        """Ack at most SQS_BATCH_SIZE handles. Returns those that failed."""

        entries = [
            {"Id": str(index), "ReceiptHandle": handle} for index, handle in enumerate(handles)
        ]
        response = self.client.delete_message_batch(QueueUrl=self.queue_url, Entries=entries)

        failed_ids = {entry["Id"] for entry in response.get("Failed", [])}
        return [handle for index, handle in enumerate(handles) if str(index) in failed_ids]

    def delete_many(self, handles: list[str]) -> list[str]:
        """Ack `handles` in batches. Returns every handle that failed."""

        failed: list[str] = []
        for chunk in chunked(handles, SQS_BATCH_SIZE):
            failed.extend(self.delete_batch(chunk))

        if failed:
            logger.warning("%d of %d handles failed to delete", len(failed), len(handles))
        return failed

from __future__ import annotations

import pytest

from lib.aws.sqs import SqsQueueBase


class FakeSqsClient:
    def __init__(self) -> None:
        self.get_queue_url_calls: list[str] = []
        self.send_calls: list[dict] = []

    def get_queue_url(self, QueueName: str):  # noqa: N803
        self.get_queue_url_calls.append(QueueName)
        return {"QueueUrl": f"https://sqs.test/{QueueName}"}

    def send_message_batch(self, QueueUrl: str, Entries: list[dict]):  # noqa: N803
        self.send_calls.append({"QueueUrl": QueueUrl, "Entries": Entries})
        return {"Successful": [{"Id": "0"}], "Failed": []}


class TestSqsQueueBaseInit:
    """Tests for SqsQueueBase construction."""

    def test_stores_an_explicit_queue_url(self):
        client = FakeSqsClient()

        result = SqsQueueBase(client=client, queue_url="https://sqs.test/q")

        assert result.queue_url == "https://sqs.test/q"
        assert client.get_queue_url_calls == []

    def test_resolves_queue_url_from_name(self):
        client = FakeSqsClient()

        result = SqsQueueBase(client=client, queue_name="my-queue")

        assert result.queue_url == "https://sqs.test/my-queue"
        assert client.get_queue_url_calls == ["my-queue"]

    def test_raises_when_url_and_name_are_missing(self):
        client = FakeSqsClient()

        with pytest.raises(ValueError):
            SqsQueueBase(client=client)


class TestSendMessageBatch:
    """Tests for SqsQueueBase.send_message_batch."""

    def test_sends_entries_on_the_stored_url(self):
        client = FakeSqsClient()
        queue = SqsQueueBase(client=client, queue_url="https://sqs.test/q")
        entries = [{"Id": "0", "MessageBody": "hello"}]

        result = queue.send_message_batch(entries)
        expected = {"Successful": [{"Id": "0"}], "Failed": []}

        assert result == expected
        assert client.send_calls == [
            {"QueueUrl": "https://sqs.test/q", "Entries": entries}
        ]

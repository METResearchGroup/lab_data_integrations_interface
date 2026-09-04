from __future__ import annotations

from lib.aws.sqs import SQS


class FakeSqsClient:
    def __init__(self) -> None:
        self.send_calls: list[dict] = []

    def send_message_batch(self, QueueUrl: str, Entries: list[dict]):  # noqa: N803
        self.send_calls.append({"QueueUrl": QueueUrl, "Entries": Entries})
        return {"Successful": [{"Id": "0"}], "Failed": []}


class TestSQSInit:
    """Tests for SQS construction."""

    def test_stores_queue_url_and_name(self):
        client = FakeSqsClient()

        result = SQS(queue_url="https://sqs.test/q", queue_name="q", client=client)

        assert result.queue_url == "https://sqs.test/q"
        assert result.queue_name == "q"


class TestSendMessageBatch:
    """Tests for SQS.send_message_batch."""

    def test_sends_entries_on_the_stored_url(self):
        client = FakeSqsClient()
        queue = SQS(queue_url="https://sqs.test/q", queue_name="q", client=client)
        entries = [{"Id": "0", "MessageBody": "hello"}]

        result = queue.send_message_batch(entries)
        expected = {"Successful": [{"Id": "0"}], "Failed": []}

        assert result == expected
        assert client.send_calls == [{"QueueUrl": "https://sqs.test/q", "Entries": entries}]

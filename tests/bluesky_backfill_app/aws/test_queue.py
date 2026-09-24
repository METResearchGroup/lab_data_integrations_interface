import json

import pytest

from bluesky_backfill_app.aws.constants import (
    IN_FLIGHT_MESSAGES_ATTRIBUTE,
    MAX_RECEIVE_COUNT,
    RECEIVE_COUNT_ATTRIBUTE,
    WAITING_MESSAGES_ATTRIBUTE,
)
from bluesky_backfill_app.aws.queue import (
    SQS_BATCH_SIZE,
    Message,
    SqsQueue,
    chunked,
    message_body,
    parse_message,
)


def raw_message(did="did:plc:a", receive_count=1, handle="handle-1"):
    return {
        "Body": json.dumps({"did": did, "run_id": "run-1"}),
        "ReceiptHandle": handle,
        "Attributes": {RECEIVE_COUNT_ATTRIBUTE: str(receive_count)},
    }


class FakeSqsClient:
    """Fails any DID listed in `fail_dids`, mirroring SendMessageBatch's shape."""

    def __init__(self, fail_dids=(), messages=(), fail_handles=(), waiting=0, in_flight=0):
        self.waiting = waiting
        self.in_flight = in_flight
        self.attribute_requests = []
        self.fail_dids = set(fail_dids)
        self.inbox = list(messages)
        self.fail_handles = set(fail_handles)
        self.batches = []
        self.receives = []
        self.deleted = []
        self.delete_batches = []

    def get_queue_url(self, QueueName):  # noqa: N803 - boto3's parameter name
        return {"QueueUrl": f"https://sqs.test/{QueueName}"}

    def send_message_batch(self, Entries, **_):  # noqa: N803 - boto3's parameter name
        self.batches.append(Entries)
        failed = [
            {"Id": entry["Id"]}
            for entry in Entries
            if json.loads(entry["MessageBody"])["did"] in self.fail_dids
        ]
        return {"Failed": failed} if failed else {}

    def receive_message(self, **kwargs):
        self.receives.append(kwargs)
        return {"Messages": [self.inbox.pop(0)]} if self.inbox else {}

    def get_queue_attributes(self, **kwargs):
        self.attribute_requests.append(kwargs)
        return {
            "Attributes": {
                WAITING_MESSAGES_ATTRIBUTE: str(self.waiting),
                IN_FLIGHT_MESSAGES_ATTRIBUTE: str(self.in_flight),
            }
        }

    def delete_message(self, ReceiptHandle, **_):  # noqa: N803 - boto3's parameter name
        self.deleted.append(ReceiptHandle)

    def delete_message_batch(self, Entries, **_):  # noqa: N803 - boto3's parameter name
        self.delete_batches.append(Entries)
        failed = [
            {"Id": entry["Id"]} for entry in Entries if entry["ReceiptHandle"] in self.fail_handles
        ]
        return {"Failed": failed} if failed else {}


def build_queue(**kwargs):
    return SqsQueue(client=FakeSqsClient(**kwargs), queue_url="https://sqs.test/q")


def test_message_body_carries_did_and_run():
    assert json.loads(message_body("did:plc:a", "run-1")) == {
        "did": "did:plc:a",
        "run_id": "run-1",
    }


def test_chunked_splits_evenly():
    assert chunked(["a", "b", "c"], 2) == [["a", "b"], ["c"]]


def test_chunked_of_empty():
    assert chunked([], 10) == []


def test_queue_url_resolves_from_the_name():
    queue = SqsQueue(client=FakeSqsClient(), queue_name="my-queue")

    assert queue.queue_url == "https://sqs.test/my-queue"


def test_explicit_queue_url_wins():
    assert build_queue().queue_url == "https://sqs.test/q"


def test_send_batch_returns_nothing_on_success():
    queue = build_queue()

    assert queue.send_batch(["did:plc:a", "did:plc:b"], "run-1") == []


def test_send_batch_names_the_failures():
    queue = build_queue(fail_dids=["did:plc:b"])

    failed = queue.send_batch(["did:plc:a", "did:plc:b", "did:plc:c"], "run-1")

    assert failed == ["did:plc:b"]


def test_send_chunks_at_the_batch_limit():
    queue = build_queue()
    dids = [f"did:plc:{n}" for n in range(25)]

    queue.send(dids, "run-1")

    assert [len(batch) for batch in queue.client.batches] == [SQS_BATCH_SIZE, SQS_BATCH_SIZE, 5]


def test_send_aggregates_failures_across_chunks():
    queue = build_queue(fail_dids=["did:plc:0", "did:plc:15"])
    dids = [f"did:plc:{n}" for n in range(25)]

    assert sorted(queue.send(dids, "run-1")) == ["did:plc:0", "did:plc:15"]


def test_send_of_empty_sends_nothing():
    queue = build_queue()

    assert queue.send([], "run-1") == []
    assert queue.client.batches == []


def test_entry_ids_are_unique_within_a_batch():
    queue = build_queue()

    queue.send([f"did:plc:{n}" for n in range(10)], "run-1")

    ids = [entry["Id"] for entry in queue.client.batches[0]]
    assert len(set(ids)) == len(ids)


def test_parse_message_reads_the_body_and_the_count():
    message = parse_message(raw_message(did="did:plc:z", receive_count=3, handle="h"))

    assert message == Message(did="did:plc:z", run_id="run-1", handle="h", receive_count=3)


def test_parse_message_treats_a_missing_count_as_a_first_delivery():
    message = parse_message(
        {"Body": json.dumps({"did": "did:plc:a", "run_id": "run-1"}), "ReceiptHandle": "h"}
    )

    assert message.receive_count == 1
    assert message.is_final_delivery is False


def test_parse_message_rejects_a_body_without_a_run_id():
    with pytest.raises(KeyError):
        parse_message({"Body": json.dumps({"did": "did:plc:a"}), "ReceiptHandle": "h"})


def test_a_message_below_the_limit_is_not_final():
    message = parse_message(raw_message(receive_count=MAX_RECEIVE_COUNT - 1))

    assert message.is_final_delivery is False


def test_a_message_at_the_limit_is_final():
    assert parse_message(raw_message(receive_count=MAX_RECEIVE_COUNT)).is_final_delivery is True


def test_an_overshooting_count_is_still_final():
    assert parse_message(raw_message(receive_count=MAX_RECEIVE_COUNT + 4)).is_final_delivery is True


def test_receive_asks_for_the_delivery_count():
    queue = build_queue(messages=[raw_message()])

    queue.receive()

    assert queue.client.receives[0]["MessageSystemAttributeNames"] == [RECEIVE_COUNT_ATTRIBUTE]
    assert queue.client.receives[0]["MaxNumberOfMessages"] == 1


def test_receive_returns_the_message():
    queue = build_queue(messages=[raw_message(did="did:plc:b")])

    message = queue.receive()

    assert message is not None
    assert message.did == "did:plc:b"


def test_receive_of_an_empty_queue_is_none():
    assert build_queue().receive() is None


def test_delete_acks_one_handle():
    queue = build_queue()

    queue.delete("handle-1")

    assert queue.client.deleted == ["handle-1"]


def test_delete_batch_returns_nothing_on_success():
    queue = build_queue()

    assert queue.delete_batch(["h1", "h2"]) == []


def test_delete_batch_names_the_failures():
    queue = build_queue(fail_handles=["h2"])

    assert queue.delete_batch(["h1", "h2", "h3"]) == ["h2"]


def test_delete_many_chunks_at_the_batch_limit():
    queue = build_queue()

    queue.delete_many([f"h{n}" for n in range(25)])

    assert [len(batch) for batch in queue.client.delete_batches] == [
        SQS_BATCH_SIZE,
        SQS_BATCH_SIZE,
        5,
    ]


def test_delete_many_aggregates_failures_across_chunks():
    queue = build_queue(fail_handles=["h0", "h15"])

    failed = queue.delete_many([f"h{n}" for n in range(25)])

    assert sorted(failed) == ["h0", "h15"]


def test_delete_many_of_empty_deletes_nothing():
    queue = build_queue()

    assert queue.delete_many([]) == []
    assert queue.client.delete_batches == []


def test_waiting_messages_reads_the_approximate_count():
    queue = build_queue(waiting=1234)

    assert queue.waiting_messages() == 1234
    assert queue.client.attribute_requests == [
        {"QueueUrl": "https://sqs.test/q", "AttributeNames": [WAITING_MESSAGES_ATTRIBUTE]}
    ]


def test_in_flight_messages_reads_the_not_visible_count():
    queue = build_queue(in_flight=20)

    assert queue.in_flight_messages() == 20
    assert queue.client.attribute_requests == [
        {"QueueUrl": "https://sqs.test/q", "AttributeNames": [IN_FLIGHT_MESSAGES_ATTRIBUTE]}
    ]

import json

from bluesky_backfill_app.aws.queue import SQS_BATCH_SIZE, SqsQueue, chunked, message_body


class FakeSqsClient:
    """Fails any DID listed in `fail_dids`, mirroring SendMessageBatch's shape."""

    def __init__(self, fail_dids=()):
        self.fail_dids = set(fail_dids)
        self.batches = []

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

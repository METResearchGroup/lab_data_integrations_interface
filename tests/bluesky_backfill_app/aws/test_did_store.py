import pytest
from botocore.exceptions import ClientError

from bluesky_backfill_app.aws.constants import (
    DID_PARTITION_KEY,
    FAILURE_DETAIL_ATTRIBUTE,
    FAILURE_REASON_ATTRIBUTE,
    MAX_FAILURE_DETAIL_CHARS,
    REASON_ACCOUNT_DEACTIVATED,
    REASON_TIMEOUT,
    REASON_UNKNOWN,
    STATUS_ATTRIBUTE,
    STATUS_DEAD_LETTERED,
    STATUS_DISCOVERED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_SHARD_ATTRIBUTE,
    STATUS_SHARD_COUNT,
)
from bluesky_backfill_app.aws.did_store import (
    DynamoDidStore,
    shard_key,
    status_shard,
    truncate_detail,
)


def client_error(code):
    return ClientError({"Error": {"Code": code}}, "PutItem")


class FakeDynamoClient:
    """Enough of the DynamoDB API for the store, keyed like the real table."""

    def __init__(self, existing=(), fail_with=None):
        self.items = {did: {} for did in existing}
        self.fail_with = fail_with
        self.puts = []
        self.updates = []
        self.queries = []

    def put_item(self, **kwargs):
        if self.fail_with:
            raise client_error(self.fail_with)
        did = kwargs["Item"][DID_PARTITION_KEY]["S"]
        if did in self.items:
            raise client_error("ConditionalCheckFailedException")
        self.items[did] = kwargs["Item"]
        self.puts.append(kwargs)

    def update_item(self, **kwargs):
        self.updates.append(kwargs)

    def query(self, **kwargs):
        self.queries.append(kwargs)
        shard = kwargs["ExpressionAttributeValues"][":shard"]["S"]
        matching = [
            item
            for item in self.items.values()
            if item and item[STATUS_SHARD_ATTRIBUTE]["S"] == shard
        ]
        return {"Items": matching[: kwargs["Limit"]]}


def build_store(**kwargs):
    return DynamoDidStore(client=FakeDynamoClient(**kwargs), table="t", concurrency=4)


def test_status_shard_is_stable_and_in_range():
    for did in ("did:plc:a", "did:plc:b", "did:plc:c"):
        key = status_shard(did, STATUS_DISCOVERED)
        assert key == status_shard(did, STATUS_DISCOVERED)
        status, shard = key.split("#")
        assert status == STATUS_DISCOVERED
        assert 0 <= int(shard) < STATUS_SHARD_COUNT


def test_status_shard_spreads_across_shards():
    shards = {status_shard(f"did:plc:{n}", STATUS_DISCOVERED) for n in range(200)}

    assert len(shards) == STATUS_SHARD_COUNT


def test_shard_key_format():
    assert shard_key(STATUS_QUEUED, 3) == f"{STATUS_QUEUED}#3"


def test_put_new_creates_at_discovered():
    store = build_store()

    assert store.put_new("did:plc:a", "run-1") is True

    item = store.client.puts[0]["Item"]
    assert item[STATUS_ATTRIBUTE]["S"] == STATUS_DISCOVERED
    assert item[STATUS_SHARD_ATTRIBUTE]["S"] == status_shard("did:plc:a", STATUS_DISCOVERED)


def test_put_new_is_conditioned_on_absence():
    store = build_store()

    store.put_new("did:plc:a", "run-1")

    assert "attribute_not_exists" in store.client.puts[0]["ConditionExpression"]


def test_put_new_returns_false_for_an_existing_did():
    store = build_store(existing=["did:plc:a"])

    assert store.put_new("did:plc:a", "run-1") is False


def test_put_new_reraises_other_errors():
    store = build_store(fail_with="ProvisionedThroughputExceededException")

    with pytest.raises(ClientError):
        store.put_new("did:plc:a", "run-1")


def test_write_counts_only_creations():
    store = build_store(existing=["did:plc:b"])

    created = store.write(["did:plc:a", "did:plc:b", "did:plc:c"], "run-1")

    assert created == 2


def test_write_persists_every_new_did():
    store = build_store()

    store.write(["did:plc:a", "did:plc:b"], "run-1")

    assert set(store.client.items) == {"did:plc:a", "did:plc:b"}


def test_write_is_a_noop_when_empty():
    store = build_store()

    assert store.write([], "run-1") == 0
    assert store.client.puts == []


def test_write_raises_on_a_non_conditional_failure():
    store = build_store(fail_with="InternalServerError")

    with pytest.raises(ClientError):
        store.write(["did:plc:a"], "run-1")


def test_set_status_rewrites_status_and_shard():
    store = build_store()

    store.set_status("did:plc:a", STATUS_QUEUED)

    update = store.client.updates[0]
    assert update["ExpressionAttributeValues"][":status"]["S"] == STATUS_QUEUED
    assert update["ExpressionAttributeValues"][":shard"]["S"] == status_shard(
        "did:plc:a", STATUS_QUEUED
    )


def test_set_status_escapes_the_reserved_word():
    store = build_store()

    store.set_status("did:plc:a", STATUS_QUEUED)

    update = store.client.updates[0]
    assert update["ExpressionAttributeNames"] == {"#status": STATUS_ATTRIBUTE}
    assert update["UpdateExpression"].startswith("SET #status = :status")


def test_set_status_writes_the_failure_fields():
    store = build_store()

    store.set_status(
        "did:plc:a",
        STATUS_FAILED,
        failure_reason=REASON_ACCOUNT_DEACTIVATED,
        failure_detail="HTTPError(400)",
    )

    update = store.client.updates[0]
    assert update["ExpressionAttributeValues"][":failure_reason"]["S"] == (
        REASON_ACCOUNT_DEACTIVATED
    )
    assert update["ExpressionAttributeValues"][":failure_detail"]["S"] == "HTTPError(400)"
    assert "REMOVE" not in update["UpdateExpression"]


def test_set_status_removes_the_failure_fields_without_a_reason():
    store = build_store()

    store.set_status("did:plc:a", STATUS_DONE)

    update = store.client.updates[0]
    assert FAILURE_REASON_ATTRIBUTE in update["UpdateExpression"].split("REMOVE")[1]
    assert FAILURE_DETAIL_ATTRIBUTE in update["UpdateExpression"].split("REMOVE")[1]
    assert ":failure_reason" not in update["ExpressionAttributeValues"]


def test_set_status_removes_a_stale_detail_when_only_a_reason_is_given():
    store = build_store()

    store.set_status("did:plc:a", STATUS_FAILED, failure_reason=REASON_UNKNOWN)

    update = store.client.updates[0]
    assert ":failure_reason" in update["ExpressionAttributeValues"]
    assert ":failure_detail" not in update["ExpressionAttributeValues"]
    assert update["UpdateExpression"].split("REMOVE")[1].strip() == FAILURE_DETAIL_ATTRIBUTE


def test_truncate_detail_leaves_a_short_error_alone():
    assert truncate_detail("boom") == "boom"


def test_truncate_detail_caps_a_stack_trace():
    detail = truncate_detail("x" * (MAX_FAILURE_DETAIL_CHARS + 500))

    assert len(detail) == MAX_FAILURE_DETAIL_CHARS + 3
    assert detail.endswith("...")


def test_set_failed_carries_the_repr_of_the_error():
    store = build_store()

    store.set_failed("did:plc:a", STATUS_DEAD_LETTERED, TimeoutError("slow"), REASON_TIMEOUT)

    values = store.client.updates[0]["ExpressionAttributeValues"]
    assert values[":status"]["S"] == STATUS_DEAD_LETTERED
    assert values[":failure_reason"]["S"] == REASON_TIMEOUT
    assert values[":failure_detail"]["S"] == "TimeoutError('slow')"


def test_query_by_status_fans_out_over_every_shard():
    store = build_store()
    store.write([f"did:plc:{n}" for n in range(50)], "run-1")

    found = store.query_by_status(STATUS_DISCOVERED, limit=50)

    assert sorted(found) == sorted(f"did:plc:{n}" for n in range(50))
    assert len(store.client.queries) == STATUS_SHARD_COUNT


def test_query_by_status_stops_at_the_limit():
    store = build_store()
    store.write([f"did:plc:{n}" for n in range(50)], "run-1")

    found = store.query_by_status(STATUS_DISCOVERED, limit=5)

    assert len(found) == 5
    assert len(store.client.queries) < STATUS_SHARD_COUNT

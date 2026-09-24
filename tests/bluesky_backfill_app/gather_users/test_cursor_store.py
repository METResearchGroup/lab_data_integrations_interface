from bluesky_backfill_app.gather_users.constants import (
    CURSOR_ATTRIBUTE,
    CURSOR_PARTITION_KEY,
)
from bluesky_backfill_app.gather_users.cursor_store import DynamoCursorStore


class FakeDynamoClient:
    def __init__(self, item=None):
        self.item = item
        self.gets = []
        self.updates = []

    def get_item(self, **kwargs):
        self.gets.append(kwargs)
        return {"Item": self.item} if self.item else {}

    def update_item(self, **kwargs):
        self.updates.append(kwargs)


def build_store(item=None):
    return DynamoCursorStore(client=FakeDynamoClient(item), table="t", run_id="run-1")


def test_key_is_the_run_id():
    assert build_store().key == {CURSOR_PARTITION_KEY: {"S": "run-1"}}


def test_read_returns_the_stored_cursor():
    assert build_store({CURSOR_ATTRIBUTE: {"S": "abc"}}).read() == "abc"


def test_read_of_a_fresh_run():
    assert build_store().read() is None


def test_read_is_consistent():
    store = build_store()

    store.read()

    assert store.client.gets[0]["ConsistentRead"] is True


def test_write_sets_the_cursor():
    store = build_store()

    store.write("abc")

    update = store.client.updates[0]
    assert update["ExpressionAttributeValues"][":cursor"]["S"] == "abc"
    assert update["UpdateExpression"].startswith(f"SET {CURSOR_ATTRIBUTE} = :cursor")

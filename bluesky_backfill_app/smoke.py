"""Smoke test against real AWS: discover, enqueue, and report statuses.

Run from repo root::

    PYTHONPATH=. uv run python -m bluesky_backfill_app.smoke --target 1000 --reset
"""

import logging

import typer
from dotenv import load_dotenv

from bluesky_backfill_app.aws.clients import build_dynamodb_client
from bluesky_backfill_app.aws.constants import (
    DID_PARTITION_KEY,
    DID_TABLE,
    STATUS_ATTRIBUTE,
)
from bluesky_backfill_app.aws.did_store import DynamoDidStore
from bluesky_backfill_app.aws.queue import SqsQueue
from bluesky_backfill_app.gather_users.constants import (
    CURSOR_PARTITION_KEY,
    CURSOR_RUN_ID,
    CURSOR_TABLE,
)
from bluesky_backfill_app.gather_users.cursor_store import DynamoCursorStore
from bluesky_backfill_app.gather_users.discovery.main import discover, new_run_id
from bluesky_backfill_app.gather_users.enqueue.main import drain
from bluesky_backfill_app.gather_users.storage.cursor import CursorTracker

logger = logging.getLogger(__name__)

DELETE_BATCH_SIZE = 25


def count_by_status(client) -> dict[str, int]:
    """Scan the whole table and tally `status`. Fine at smoke-test sizes only."""

    counts: dict[str, int] = {}
    paginator = client.get_paginator("scan")

    for page in paginator.paginate(
        TableName=DID_TABLE,
        ProjectionExpression="#status",
        ExpressionAttributeNames={"#status": STATUS_ATTRIBUTE},
    ):
        for item in page["Items"]:
            status = item[STATUS_ATTRIBUTE]["S"]
            counts[status] = counts.get(status, 0) + 1

    return counts


def clear_tables(client) -> None:
    """Delete every DID and the cursor item, so a rerun starts from nothing."""

    paginator = client.get_paginator("scan")
    keys = [
        item[DID_PARTITION_KEY]
        for page in paginator.paginate(TableName=DID_TABLE, ProjectionExpression=DID_PARTITION_KEY)
        for item in page["Items"]
    ]

    for start in range(0, len(keys), DELETE_BATCH_SIZE):
        client.batch_write_item(
            RequestItems={
                DID_TABLE: [
                    {"DeleteRequest": {"Key": {DID_PARTITION_KEY: key}}}
                    for key in keys[start : start + DELETE_BATCH_SIZE]
                ]
            }
        )

    client.delete_item(TableName=CURSOR_TABLE, Key={CURSOR_PARTITION_KEY: {"S": CURSOR_RUN_ID}})
    print(f"cleared {len(keys)} dids and the cursor")


def main(
    target: int = typer.Option(1000, help="DIDs to discover"),
    reset: bool = typer.Option(False, help="Delete every DID and the cursor before starting"),
):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    load_dotenv()

    client = build_dynamodb_client()
    if reset:
        clear_tables(client)

    store = DynamoDidStore()

    print("\n== discover ==")
    discover(store, CursorTracker(DynamoCursorStore()), new_run_id(), target)

    cursor, count = DynamoCursorStore().read()
    print(f"cursor:           {cursor}")
    print(f"discovered_count: {count}")
    print(f"statuses:         {count_by_status(client)}")

    print("\n== enqueue ==")
    sent = drain(store, SqsQueue(), new_run_id())
    print(f"sent:             {sent}")
    print(f"statuses:         {count_by_status(client)}")


if __name__ == "__main__":
    typer.run(main)

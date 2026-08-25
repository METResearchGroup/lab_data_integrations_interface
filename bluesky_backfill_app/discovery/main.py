"""Page listRepos, buffer DIDs, write them to DynamoDB, stop at target.

Run from repo root::

    PYTHONPATH=. uv run python -m bluesky_backfill_app.discovery.main
"""

import logging
from uuid import uuid4

from bluesky_backfill_app.aws.cursor_store import DynamoCursorStore
from bluesky_backfill_app.aws.did_store import DynamoDidStore
from bluesky_backfill_app.constants import TARGET_DID_COUNT
from bluesky_backfill_app.storage.buffer import DidBuffer
from bluesky_backfill_app.storage.cursor import CursorTracker

logger = logging.getLogger(__name__)


def new_run_id() -> str:
    return str(uuid4())


def build_cursor_tracker() -> CursorTracker:
    return CursorTracker(DynamoCursorStore())


def flush(buffer: DidBuffer, store: DynamoDidStore, tracker: CursorTracker, run_id: str) -> None:
    """Write the buffer, then advance the cursor. Never the reverse."""

    raise NotImplementedError


def discover(
    store: DynamoDidStore,
    tracker: CursorTracker,
    run_id: str,
    target: int = TARGET_DID_COUNT,
) -> None:
    """Page from the stored cursor until `target` DIDs exist, flushing on thresholds."""

    raise NotImplementedError


def main() -> None:
    raise NotImplementedError


if __name__ == "__main__":
    main()

import logging
import time

import pyarrow as pa
from libipld import decode_car

from bluesky_backfill_app.aws.constants import REASON_CAR_DECODE_ERROR, REASON_SCHEMA_MISMATCH
from bluesky_backfill_app.fetch_repos.decode.records import decode
from bluesky_backfill_app.fetch_repos.failures import RepoFailure
from bluesky_backfill_app.fetch_repos.landing.writer import build_tables
from bluesky_backfill_app.fetch_repos.network.errors import classify
from bluesky_backfill_app.fetch_repos.network.get_repo import fetch_repo
from bluesky_ingestion_jetstream.constants import RecordType
from lib.timestamp_utils import get_current_datetime

logger = logging.getLogger(__name__)


def load_repo(did: str, run_id: str) -> dict[RecordType, pa.Table]:
    """Fetch and decode one repo into Arrow tables. Raises `RepoFailure`."""

    started = time.monotonic()
    try:
        car = fetch_repo(did)
    except Exception as error:
        raise RepoFailure(classify(error), error) from error

    car_size = len(car)
    fetched = time.monotonic()
    try:
        header, blocks = decode_car(car)
        # Blocks are copies; free the CAR before the walk, and blocks before building tables.
        del car
        rows = decode(did, header, blocks, get_current_datetime())
        del blocks
    except Exception as error:
        raise RepoFailure(REASON_CAR_DECODE_ERROR, error) from error

    try:
        tables = build_tables(rows, run_id)
    except Exception as error:
        raise RepoFailure(REASON_SCHEMA_MISMATCH, error) from error

    logger.info(
        "%s %d rows from %d bytes, fetch %.2fs, decode %.2fs",
        did,
        sum(table.num_rows for table in tables.values()),
        car_size,
        fetched - started,
        time.monotonic() - fetched,
    )
    return tables

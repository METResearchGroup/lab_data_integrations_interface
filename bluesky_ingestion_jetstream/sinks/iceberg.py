"""Commit flushed rows to Iceberg, or dead-letter them.

The retry wraps the whole `append`, because the append *is* the S3 writes and the
Glue commit together -- there is no separate upload step to retry on its own, and
the Glue swap at the end is the only point where anything becomes visible. So a
retried attempt cannot double-write a table; it can only leave orphan files
behind from the attempt it abandoned.

This runs synchronously inside the async read loop, so its worst case is time the
Jetstream socket spends undrained. That is the reason for three attempts rather
than ten, and for the client timeouts in `aws/constants.py`.
"""

import logging
from collections.abc import Callable
from uuid import uuid4

from pyiceberg.table import Table

from bluesky_ingestion_jetstream.aws.dead_letter import write_dead_letter
from bluesky_ingestion_jetstream.aws.iceberg_writer import (
    already_committed,
    append_once,
    build_append_table,
)
from bluesky_ingestion_jetstream.aws.retry import retry_iceberg_commit

logger = logging.getLogger(__name__)


class IcebergSink:
    """Writes each record type to its own Iceberg table.

    Holds the `run_id` because it is fixed for the life of the process; threading
    it down through the flush signature would be churn for a value that cannot
    vary per row.
    """

    def __init__(
        self,
        tables: dict[str, Table],
        run_id: str,
        dead_letter: Callable[..., str] = write_dead_letter,
    ) -> None:
        self.tables = tables
        self.run_id = run_id
        self.dead_letter = dead_letter

    def write(self, record_type: str, rows: list[dict]) -> None:
        """Commit one record type's batch, dead-lettering it if that fails.

        Called once per record type per flush rather than once per flush, so a
        table that is failing does not hold up the three that are not.
        """

        if not rows:
            return

        # Stamped in place: a flush batch can be large, and copying every row to
        # add one fixed key costs more than it explains. The buffer clears
        # straight afterwards, so nothing else observes the mutation.
        for row in rows:
            row["run_id"] = self.run_id

        try:
            self._commit(record_type, rows)
        except Exception:
            logger.warning(
                "commit failed for %d %s rows; dead-lettering",
                len(rows),
                record_type,
                exc_info=True,
            )
            self.dead_letter(record_type, rows, self.run_id)

    def _commit(self, record_type: str, rows: list[dict]) -> None:
        """Append with retries, skipping the work if a retry finds it already done."""

        table = self.tables[record_type]
        append_table = build_append_table(table, rows)
        flush_id = str(uuid4())
        attempts = 0

        @retry_iceberg_commit()
        def commit() -> None:
            nonlocal attempts
            attempts += 1

            # Only from the second attempt on: on the first there is nothing to
            # have succeeded yet, and the check costs a Glue GetTable.
            if attempts > 1 and already_committed(table, flush_id):
                logger.warning(
                    "commit for %d %s rows had already landed; not repeating it",
                    len(rows),
                    record_type,
                )
                return

            append_once(table, append_table, flush_id)

        commit()

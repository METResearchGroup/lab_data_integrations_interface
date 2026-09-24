import logging

from bluesky_backfill_app.aws.constants import (
    PERMANENT_REASONS,
    REASON_LANDING_WRITE_ERROR,
    STATUS_DEAD_LETTERED,
    STATUS_FAILED,
    STATUS_QUEUED,
)
from bluesky_backfill_app.aws.did_store import DynamoDidStore
from bluesky_backfill_app.aws.queue import Message, SqsQueue
from bluesky_backfill_app.telemetry.instruments import record_repo_failure

logger = logging.getLogger(__name__)


class RepoFailure(Exception):
    def __init__(self, reason: str, error: BaseException):
        super().__init__(reason, error)
        self.reason = reason
        self.error = error


def record_failure(
    did_store: DynamoDidStore,
    queue: SqsQueue,
    message: Message,
    failure: RepoFailure,
) -> None:
    """Permanent: `failed` + ack. Final delivery: `dead_lettered`. Otherwise left to redeliver."""

    if failure.reason in PERMANENT_REASONS:
        did_store.set_failed(message.did, STATUS_FAILED, failure.error, failure.reason)
        queue.delete(message.handle)
        logger.info("%s failed: %s", message.did, failure.reason)
        record_repo_failure(failure.reason, STATUS_FAILED)
    elif message.is_final_delivery:
        did_store.set_failed(message.did, STATUS_DEAD_LETTERED, failure.error, failure.reason)
        logger.warning("%s dead-lettered: %s %r", message.did, failure.reason, failure.error)
        record_repo_failure(failure.reason, STATUS_DEAD_LETTERED)
    else:
        logger.warning(
            "%s delivery %d failed: %s %r",
            message.did,
            message.receive_count,
            failure.reason,
            failure.error,
        )
        record_repo_failure(failure.reason, STATUS_QUEUED)


def record_flush_failure(
    did_store: DynamoDidStore,
    messages: list[Message],
    error: BaseException,
) -> None:
    for message in messages:
        if message.is_final_delivery:
            did_store.set_failed(
                message.did, STATUS_DEAD_LETTERED, error, REASON_LANDING_WRITE_ERROR
            )
            record_repo_failure(REASON_LANDING_WRITE_ERROR, STATUS_DEAD_LETTERED)
        else:
            record_repo_failure(REASON_LANDING_WRITE_ERROR, STATUS_QUEUED)

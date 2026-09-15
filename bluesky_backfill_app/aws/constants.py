# One item per discovered repo. Created by Terraform.
DID_TABLE = "bluesky_backfill_dids"
DID_PARTITION_KEY = "did"
DISCOVERED_AT_ATTRIBUTE = "discovered_at"
UPDATED_AT_ATTRIBUTE = "updated_at"
RUN_ID_ATTRIBUTE = "run_id"

STATUS_ATTRIBUTE = "status"
STATUS_DISCOVERED = "discovered"
STATUS_QUEUED = "queued"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
# Out of deliveries; the message is in the DLQ.
STATUS_DEAD_LETTERED = "dead_lettered"

STATUSES = (
    STATUS_DISCOVERED,
    STATUS_QUEUED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_DEAD_LETTERED,
)

# Reason is a code; detail is the raw error. Only set for FAILURE_STATUSES.
FAILURE_REASON_ATTRIBUTE = "failure_reason"
FAILURE_DETAIL_ATTRIBUTE = "failure_detail"
FAILURE_STATUSES = (STATUS_FAILED, STATUS_DEAD_LETTERED)

MAX_FAILURE_DETAIL_CHARS = 1024

REASON_ACCOUNT_DEACTIVATED = "account_deactivated"
REASON_ACCOUNT_TAKENDOWN = "account_takendown"
REASON_REPO_NOT_FOUND = "repo_not_found"
REASON_CAR_DECODE_ERROR = "car_decode_error"
REASON_SCHEMA_MISMATCH = "schema_mismatch"
REASON_HTTP_429 = "http_429"
REASON_HTTP_5XX = "http_5xx"
REASON_TIMEOUT = "timeout"
REASON_CONNECTION_ERROR = "connection_error"
REASON_LANDING_WRITE_ERROR = "landing_write_error"
# Unclassified. Not retryable.
REASON_UNKNOWN = "unknown"

PERMANENT_REASONS = (
    REASON_ACCOUNT_DEACTIVATED,
    REASON_ACCOUNT_TAKENDOWN,
    REASON_REPO_NOT_FOUND,
)
# Our bugs; retryable once fixed.
BUG_REASONS = (REASON_CAR_DECODE_ERROR, REASON_SCHEMA_MISMATCH)
TRANSIENT_REASONS = (
    REASON_HTTP_429,
    REASON_HTTP_5XX,
    REASON_TIMEOUT,
    REASON_CONNECTION_ERROR,
    REASON_LANDING_WRITE_ERROR,
)

RETRYABLE_REASONS = frozenset(TRANSIENT_REASONS + BUG_REASONS)
REASONS = PERMANENT_REASONS + BUG_REASONS + TRANSIENT_REASONS + (REASON_UNKNOWN,)

# GSI key is `{status}#{shard}`; queries fan out across the shards.
STATUS_INDEX = "status_index"
STATUS_SHARD_ATTRIBUTE = "status_shard"
STATUS_SHARD_COUNT = 10

# Concurrent conditional PutItems per flush, and UpdateItems per status change.
WRITE_CONCURRENCY = 16

# Created by Terraform.
QUEUE_NAME = "bluesky-backfill-dids"
DLQ_NAME = f"{QUEUE_NAME}-dlq"

# Deliveries before SQS moves a message to the DLQ. Matches the redrive policy.
MAX_RECEIVE_COUNT = 5

# Long-poll wait per receive. 20 is the SQS max.
RECEIVE_WAIT_SECONDS = 20
# SQS attribute holding a message's delivery count.
RECEIVE_COUNT_ATTRIBUTE = "ApproximateReceiveCount"

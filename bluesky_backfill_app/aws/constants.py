AWS_REGION = "us-east-2"

# One item per discovered repo. Created by Terraform.
DID_TABLE = "bluesky_backfill_dids"
DID_PARTITION_KEY = "did"
DISCOVERED_AT_ATTRIBUTE = "discovered_at"
RUN_ID_ATTRIBUTE = "run_id"

STATUS_ATTRIBUTE = "status"
STATUS_DISCOVERED = "discovered"
STATUS_QUEUED = "queued"
STATUS_DONE = "done"
STATUS_FAILED = "failed"

STATUSES = (STATUS_DISCOVERED, STATUS_QUEUED, STATUS_DONE, STATUS_FAILED)

# GSI key is `{status}#{shard}`; queries fan out across the shards.
STATUS_INDEX = "status_index"
STATUS_SHARD_ATTRIBUTE = "status_shard"
STATUS_SHARD_COUNT = 10

# Concurrent conditional PutItems per flush.
WRITE_CONCURRENCY = 16

CURSOR_TABLE = "bluesky_backfill_cursor"
CURSOR_RUN_ID = "bluesky_backfill"
CURSOR_PARTITION_KEY = "run_id"
CURSOR_ATTRIBUTE = "list_repos_cursor"
DISCOVERED_COUNT_ATTRIBUTE = "discovered_count"

DYNAMODB_MAX_ATTEMPTS = 3
DYNAMODB_CONNECT_TIMEOUT_SECONDS = 3.0
DYNAMODB_READ_TIMEOUT_SECONDS = 5.0

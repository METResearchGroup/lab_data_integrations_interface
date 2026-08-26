AWS_REGION = "us-east-2"

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

STATUSES = (STATUS_DISCOVERED, STATUS_QUEUED, STATUS_DONE, STATUS_FAILED)

# GSI key is `{status}#{shard}`; queries fan out across the shards.
STATUS_INDEX = "status_index"
STATUS_SHARD_ATTRIBUTE = "status_shard"
STATUS_SHARD_COUNT = 10

# Concurrent conditional PutItems per flush, and UpdateItems per status change.
WRITE_CONCURRENCY = 16

# Created by Terraform.
QUEUE_NAME = "bluesky-backfill-dids"

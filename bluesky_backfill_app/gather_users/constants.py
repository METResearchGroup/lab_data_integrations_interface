# The listRepos cursor and running DID count. Created by Terraform.
CURSOR_TABLE = "bluesky_backfill_cursor"
CURSOR_RUN_ID = "bluesky_backfill"
CURSOR_PARTITION_KEY = "run_id"
CURSOR_ATTRIBUTE = "list_repos_cursor"
DISCOVERED_COUNT_ATTRIBUTE = "discovered_count"

# Flush on whichever trips first.
MAX_BUFFER_DIDS = 10_000
MAX_BUFFER_AGE_SECONDS = 10.0 * 60.0

FLUSH_REASON_COUNT = "count"
FLUSH_REASON_AGE = "age"
FLUSH_REASON_TARGET = "target"
FLUSH_REASON_FINAL = "final"

LIST_REPOS_URL = "https://relay1.us-east.bsky.network/xrpc/com.atproto.sync.listRepos"
LIST_REPOS_PAGE_SIZE = 1000
LIST_REPOS_TIMEOUT_SECONDS = 120
LIST_REPOS_MAX_ATTEMPTS = 5

# DIDs pulled from the status index per drain pass.
ENQUEUE_PAGE_SIZE = 500

# Retried without a Retry-After header, and on transport failures.
INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 60.0
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

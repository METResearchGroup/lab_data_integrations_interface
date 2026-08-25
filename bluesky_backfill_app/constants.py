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

# Retried without a Retry-After header, and on transport failures.
INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 60.0
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

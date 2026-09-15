GET_REPO_URL = "https://relay1.us-east.bsky.network/xrpc/com.atproto.sync.getRepo"
GET_REPO_TIMEOUT_SECONDS = 60
GET_REPO_MAX_ATTEMPTS = 5
# Whole fetch, retries included.
GET_REPO_DEADLINE_SECONDS = 15.0 * 60.0
GET_REPO_READ_CHUNK_BYTES = 1024 * 1024
MAX_ERROR_BODY_BYTES = 4096

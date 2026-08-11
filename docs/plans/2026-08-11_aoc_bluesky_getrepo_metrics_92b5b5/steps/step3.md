# Step 3: Load AOC’s repo once and index post records

## Goal

Implement one relay `getRepo` fetch for AOC’s DID, decode the CAR/MST, and return a dict of `app.bsky.feed.post` records keyed by at-URI for join in Step 4.

## Scope

- **Caller path segment:** `main` → `fetch_and_index_posts(relay, did)`
- **Slice:** `get_repo` → decode → filter post collection → URI index
- **Out of scope:** author feed, metric column mapping, CSV write, per-post `getRepo` calls

## Files to inspect

- `experimentation/aoc_followers_backfill/mst.py` — `decode_repo(repo_bytes) -> (did, records)`
- `experimentation/aoc_followers_backfill/backfill.py` — how posts are filtered by `$type`
- `experimentation/aoc_followers_backfill/client.py` — `create_relay_client` / `RELAY_BASE_URL`
- `strategy_planning/2026-07-15_getrepo_return_type.md` — post record fields
- `experimentation/aoc_posts_getrepo_metrics/repo.py` (stub)

## Files allowed to change

- `experimentation/aoc_posts_getrepo_metrics/repo.py`
- **New** `experimentation/aoc_posts_getrepo_metrics/mst.py` **only if** choosing copy-over-import; otherwise import `decode_repo` from `experimentation.aoc_followers_backfill.mst` (preferred to stay DRY)
- **New** `tests/experimentation/aoc_posts_getrepo_metrics/test_repo.py`
- `experimentation/aoc_posts_getrepo_metrics/constants.py` — add `POST_COLLECTION = "app.bsky.feed.post"` if useful

## Files forbidden to change

- `experimentation/aoc_followers_backfill/**` (read/import only; do not edit)
- `experimentation/aoc_posts_getrepo_metrics/feed.py` (done in Step 2)
- `experimentation/aoc_posts_getrepo_metrics/metrics.py`
- `experimentation/aoc_posts_getrepo_metrics/output.py`
- `data_platform/**`

## Contracts

### `fetch_and_index_posts(relay_client, did: str) -> dict[str, dict]`

1. Call **once**: `relay_client.com.atproto.sync.get_repo({"did": did})` → raw CAR bytes.
2. Decode with `decode_repo(repo_bytes)` → `(repo_did, records)`.
3. Optionally assert `repo_did == did` (raise `ValueError` on mismatch).
4. Build `{uri: record for uri, record in records.items() if record.get("$type") == "app.bsky.feed.post"}`.
5. Return that dict. Do not filter by date; indexing all posts in the repo is fine (join in Step 4 selects the ≥50 feed URIs).

**Hard rule:** this function must not loop `get_repo` per post URI. One network call per invocation.

On SDK/network failure: propagate the exception (caller/`main` may catch later; do not swallow).

### Decode reuse decision

Prefer:

```text
from experimentation.aoc_followers_backfill.mst import decode_repo
```

If that import is undesirable for package isolation, copy `mst.py` verbatim into this package and note the copy in the module docstring. Do not reimplement MST walking from scratch.

## Test design (TDD)

File: `tests/experimentation/aoc_posts_getrepo_metrics/test_repo.py`

| Test | Given / when / then |
|------|---------------------|
| `test_fetch_and_index_calls_get_repo_once` | Mock relay; `get_repo` returns fixture bytes; monkeypatch `decode_repo` to return two posts + one like; assert `get_repo` call count == 1 |
| `test_fetch_and_index_keeps_only_posts` | Decoded records include post + like + follow → output keys only post URIs |
| `test_fetch_and_index_keys_are_at_uris` | Every key starts with `at://` and contains `/app.bsky.feed.post/` |
| `test_fetch_and_index_raises_on_did_mismatch` | `decode_repo` returns different DID than requested → `ValueError` |

Do not hit the live relay in unit tests. Fixture: tiny fake `records` dict from the monkeypatched decoder; CAR bytes can be `b"fake"`.

## Implementation order

1. Write tests (failing).
2. Implement `fetch_and_index_posts`.
3. Confirm single `get_repo` call via mock assertion.

## Must pass

```bash
uv run pytest tests/experimentation/aoc_posts_getrepo_metrics/test_repo.py -q
```

Expected: all pass.

```bash
uv run pytest tests/experimentation/aoc_posts_getrepo_metrics/ -q
```

Expected: Step 2 + Step 3 tests all pass.

## Must fail

- Implementation that calls `get_repo` inside a per-URI loop (caught by `test_fetch_and_index_calls_get_repo_once`).
- Live network in unit tests.

## Manual live check (optional)

```bash
PYTHONPATH=. uv run python -c "
from experimentation.aoc_posts_getrepo_metrics.client import create_public_client, create_relay_client
from experimentation.aoc_posts_getrepo_metrics.constants import TARGET_HANDLE
from experimentation.aoc_posts_getrepo_metrics.feed import resolve_did
from experimentation.aoc_posts_getrepo_metrics.repo import fetch_and_index_posts
did = resolve_did(create_public_client(), TARGET_HANDLE)
idx = fetch_and_index_posts(create_relay_client(), did)
print(len(idx))
"
```

Expected: prints a positive integer (AOC historically had hundreds of posts).

## Done when

- Offline repo tests green.
- One `getRepo` per `fetch_and_index_posts` call.
- Prior experiment package unmodified.

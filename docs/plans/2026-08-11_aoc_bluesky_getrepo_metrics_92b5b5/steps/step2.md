# Step 2: Collect ≥50 latest AOC post IDs via getAuthorFeed

## Goal

Implement public AppView listing so `fetch_latest_post_uris` returns at least `MIN_POSTS` (50) URIs for posts authored by AOC, newest-first via paginated `getAuthorFeed`.

## Scope

- **Caller path segment:** `main` → `resolve_did` → `fetch_latest_post_uris`
- **Slice:** resolve handle → page feed → filter to AOC-authored posts → collect URIs until `min_posts`
- **Out of scope:** `getRepo`, metrics derivation, CSV output, authenticated entryway client

## Files to inspect

- `experimentation/aoc_posts_getrepo_metrics/feed.py` (stub from Step 1)
- `experimentation/aoc_posts_getrepo_metrics/constants.py`
- `experimentation/aoc_posts_getrepo_metrics/client.py`
- `experimentation/aoc_followers_backfill/discovery.py` — `get_author_feed` usage pattern
- `experimentation/helpers/posts.py` — simpler feed fetch example

## Files allowed to change

- `experimentation/aoc_posts_getrepo_metrics/feed.py`
- **New** `tests/experimentation/aoc_posts_getrepo_metrics/test_feed.py`
- **New** `tests/experimentation/aoc_posts_getrepo_metrics/__init__.py` (empty) if needed for discovery
- `experimentation/aoc_posts_getrepo_metrics/README.md` (document feed behavior only if needed)

## Files forbidden to change

- `experimentation/aoc_followers_backfill/**`
- `experimentation/aoc_posts_getrepo_metrics/repo.py`
- `experimentation/aoc_posts_getrepo_metrics/metrics.py`
- `experimentation/aoc_posts_getrepo_metrics/output.py`
- `data_platform/**`

## Contracts

### `resolve_did(client, handle: str) -> str`

- Call `client.app.bsky.actor.get_profile({"actor": handle})`.
- Return `.did`.
- Raise clearly if profile lookup fails (propagate SDK exception; no silent empty string).

### `fetch_latest_post_uris(client, actor: str, *, min_posts: int) -> list[str]`

Behavior:

1. Page `client.app.bsky.feed.get_author_feed` with `actor`, `limit=AUTHOR_FEED_PAGE_SIZE`, and cursor pagination.
2. For each feed item, keep the post only when `item.post.author.did == actor` **or** (if actor was a handle) `item.post.author.handle` matches the resolved identity — prefer comparing DID: pass DID as `actor` from `main`.
3. Skip feed items that are reposts of another author’s post (author DID ≠ AOC DID).
4. Append `item.post.uri` in feed order (newest first as returned by AppView).
5. Stop when `len(uris) >= min_posts` or the feed is exhausted (`cursor` absent / empty page).
6. If fewer than `min_posts` after exhaustion, raise `ValueError` with the count collected.

Do **not** call `getPosts`, `searchPosts`, or any engagement endpoint.

Return type: `list[str]` of at-URIs (e.g. `at://did:plc:…/app.bsky.feed.post/…`).

## Test design (TDD — write failing tests first)

File: `tests/experimentation/aoc_posts_getrepo_metrics/test_feed.py`

Use fake client objects (simple namespaces / MagicMock) — no network.

| Test | Given / when / then |
|------|---------------------|
| `test_resolve_did_returns_profile_did` | Fake profile `.did = "did:plc:aoc"` → assert return equals that DID |
| `test_fetch_stops_at_min_posts` | Two pages of AOC posts; `min_posts=3` → exactly 3 URIs; second page partially consumed |
| `test_fetch_skips_reposts_of_others` | Feed contains one item whose `post.author.did` ≠ actor → URI omitted |
| `test_fetch_raises_if_insufficient` | Feed exhausts with 2 AOC posts; `min_posts=50` → `ValueError` |
| `test_fetch_paginates_with_cursor` | First response has `cursor`; assert second call receives that cursor |

## Implementation order

1. Write the five tests above (expect fail / NotImplementedError).
2. Implement `resolve_did`.
3. Implement `fetch_latest_post_uris` pagination + author filter + insufficient error.
4. Re-run tests until green.

## Must pass

```bash
uv run pytest tests/experimentation/aoc_posts_getrepo_metrics/test_feed.py -q
```

Expected: all tests pass (exit code 0).

## Must fail

- Any test that requires network.
- Changing `MIN_POSTS` below 50 in constants (plan forbids).

## Manual live check (optional, not CI)

```bash
PYTHONPATH=. uv run python -c "
from experimentation.aoc_posts_getrepo_metrics.client import create_public_client
from experimentation.aoc_posts_getrepo_metrics.constants import TARGET_HANDLE, MIN_POSTS
from experimentation.aoc_posts_getrepo_metrics.feed import resolve_did, fetch_latest_post_uris
c = create_public_client()
did = resolve_did(c, TARGET_HANDLE)
uris = fetch_latest_post_uris(c, did, min_posts=MIN_POSTS)
print(len(uris), uris[0])
"
```

Expected: prints an integer `>= 50` and one `at://…/app.bsky.feed.post/…` URI.

## Done when

- Offline feed tests green.
- `main` still wires to these functions (may still fail later on repo/metrics stubs).

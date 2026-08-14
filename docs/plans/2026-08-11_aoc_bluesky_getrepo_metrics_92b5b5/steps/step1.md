# Step 1: Scaffold the experiment package

## Goal

Create a new experiment package with frozen file layout, constants, client factories, and a thin `main.py` that shows the end-to-end call order with stubbed bodies. No network I/O and no metric logic in this step.

## Scope (implement-from-spec Phase 0)

- **Caller:** `experimentation/aoc_posts_getrepo_metrics/main.py` → `main()`
- **Slice:** resolve → list post IDs → load repo → derive metrics → write outputs (stubs only)
- **Out of scope:** real `getAuthorFeed` pagination, real `getRepo` decode, CSV writing behavior, pytest

## Files to inspect

- `experimentation/aoc_followers_backfill/client.py` — public AppView vs relay client split
- `experimentation/aoc_followers_backfill/constants.py` — AOC handle `aoc.bsky.social`
- `experimentation/aoc_followers_backfill/mst.py` — `decode_repo` to decide import-vs-copy in Step 3
- `lib/timestamp_utils.py` — `get_current_timestamp()` for run folders
- `docs/plans/2026-08-11_aoc_bluesky_getrepo_metrics_92b5b5/plan.md` — confirmed decisions

## Files allowed to change

- **New** `experimentation/aoc_posts_getrepo_metrics/__init__.py` (empty)
- **New** `experimentation/aoc_posts_getrepo_metrics/constants.py`
- **New** `experimentation/aoc_posts_getrepo_metrics/client.py`
- **New** `experimentation/aoc_posts_getrepo_metrics/feed.py` (stub)
- **New** `experimentation/aoc_posts_getrepo_metrics/repo.py` (stub)
- **New** `experimentation/aoc_posts_getrepo_metrics/metrics.py` (stub)
- **New** `experimentation/aoc_posts_getrepo_metrics/output.py` (stub)
- **New** `experimentation/aoc_posts_getrepo_metrics/main.py` (wiring only)
- **New** `experimentation/aoc_posts_getrepo_metrics/README.md` (how to run; one short paragraph)

## Files forbidden to change

- `experimentation/aoc_followers_backfill/**` (any file)
- `data_platform/**`
- `bluesky_ingestion_jetstream/**`
- Any production ingestion YAML or sync script

## Contracts to freeze (stubs)

### `constants.py`

| Name | Value / meaning |
|------|-----------------|
| `TARGET_HANDLE` | `aoc.bsky.social` |
| `MIN_POSTS` | `50` |
| `AUTHOR_FEED_PAGE_SIZE` | `100` (AppView max page size) |
| `RELAY_BASE_URL` | `https://bsky.network` |
| `PUBLIC_APPVIEW_BASE_URL` | `https://public.api.bsky.app` |
| `OUTPUT_ROOT` | package-local `data/` directory |
| `CSV_FIELDNAMES` | ordered list matching Step 4 schema (declare names here; populate logic later) |

`CSV_FIELDNAMES` must include exactly these columns in this order:

1. `post_uri`
2. `post_rkey`
3. `created_at`
4. `deleted`
5. `deleted_at`
6. `post_type`
7. `has_image`
8. `has_video`
9. `langs`
10. `like_count`
11. `reply_count`
12. `repost_count`
13. `quote_count`
14. `save_count`
15. `counts_read_at`

### `client.py`

```text
create_public_client() -> Client
  # Client(base_url=PUBLIC_APPVIEW_BASE_URL); no login

create_relay_client() -> Client
  # Client(base_url=RELAY_BASE_URL); no login
```

Mirror the behavior of `experimentation/aoc_followers_backfill/client.py` `create_public_client` / `create_relay_client`. Do not require `BLUESKY_HANDLE` / `BLUESKY_PASSWORD` for this experiment.

### Stub signatures (bodies: `raise NotImplementedError`)

```text
feed.resolve_did(client, handle: str) -> str
feed.fetch_latest_post_uris(client, actor: str, *, min_posts: int) -> list[str]

repo.fetch_and_index_posts(relay_client, did: str) -> dict[str, dict]
  # maps post URI -> decoded app.bsky.feed.post record

metrics.derive_row(post_uri: str, record: dict | None) -> dict
metrics.derive_rows(post_uris: list[str], posts_by_uri: dict[str, dict]) -> list[dict]

output.write_outputs(rows: list[dict], *, metadata: dict, sync_timestamp: str) -> Path
```

### `main.py` call order (must compile / import)

1. `sync_timestamp = get_current_timestamp()`
2. `public = create_public_client()`
3. `did = resolve_did(public, TARGET_HANDLE)`
4. `uris = fetch_latest_post_uris(public, did, min_posts=MIN_POSTS)`
5. `relay = create_relay_client()`
6. `posts_by_uri = fetch_and_index_posts(relay, did)`
7. `rows = derive_rows(uris, posts_by_uri)`
8. `write_outputs(rows, metadata={...}, sync_timestamp=sync_timestamp)`
9. Print output path and row count

Stub callees may raise `NotImplementedError`; `main` must still show this sequence.

## Implementation order

1. Create package directory and empty `__init__.py`.
2. Add `constants.py` with frozen values and `CSV_FIELDNAMES`.
3. Add `client.py` with real client factories (copy pattern from prior experiment; small enough to implement now — not metric logic).
4. Add stub modules with signatures above.
5. Wire `main.py` call order.
6. Add README with exact run command.

## Must pass

```bash
PYTHONPATH=. uv run python -c "import experimentation.aoc_posts_getrepo_metrics.main as m; print('ok')"
```

Expected stdout includes `ok`. Import must succeed.

```bash
PYTHONPATH=. uv run python -c "from experimentation.aoc_posts_getrepo_metrics.constants import MIN_POSTS, TARGET_HANDLE, CSV_FIELDNAMES; assert MIN_POSTS == 50; assert TARGET_HANDLE == 'aoc.bsky.social'; assert CSV_FIELDNAMES[0] == 'post_uri'; assert 'counts_read_at' in CSV_FIELDNAMES; print(len(CSV_FIELDNAMES))"
```

Expected: prints `15`.

## Must fail (until later steps)

```bash
PYTHONPATH=. uv run python -c "from experimentation.aoc_posts_getrepo_metrics.feed import fetch_latest_post_uris; fetch_latest_post_uris(None, 'x', min_posts=50)"
```

Expected: `NotImplementedError` (or equivalent stub failure). Same for `repo.fetch_and_index_posts` and `metrics.derive_row`.

## Done when

- Package tree exists; imports resolve; `main.py` encodes the caller path; stubs raise; no live API calls in Step 1.

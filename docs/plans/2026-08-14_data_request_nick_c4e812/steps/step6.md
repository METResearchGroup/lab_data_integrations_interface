# Step 6: Resumable getPosts into posts.csv

Fill pending rows in an existing `posts.csv` using public AppView `getPosts`. Do not call getRepo. Skip URIs whose `hydration_status` is already `ok`. Use one global URI list per mode, batched 25. Write back into the same run folder.

## Scope

- **Caller:** `main.run(..., from_dir=..., hydrate=...)` after a `--hydrate none` folder exists.
- **Slice:** choose URIs by mode, call `get_posts` on `public.api.bsky.app`, merge into `posts.csv`, append getPosts errors, update `run_metadata.json`.
- **Out of scope:** Re-downloading repos, changing activity or graph CSVs, inventing saves or unfollows.

## Files

### Inspect

- `experiments/data_request_2026_08_14/EXPECTED_FILES.md` (`posts.csv` columns and `hydration_status`)
- `experimentation/aoc_posts_getrepo_metrics/constants.py` (`GET_POSTS_MAX_URIS = 25`)
- `experimentation/aoc_posts_getrepo_metrics/enrichment.py` (batch `get_posts` loop; this experiment needs text and media too, so do not reuse `fetch_engagement_by_uri` as-is)
- `experimentation/aoc_followers_backfill/client.py` (`create_public_client`)
- `experiments/data_request_2026_08_14/output.py` (rewrite `posts.csv` and metadata)

### Allowed to change

- `experiments/data_request_2026_08_14/hydrate.py` (create)
- `experiments/data_request_2026_08_14/constants.py` (`GET_POSTS_MAX_URIS = 25`)
- `experiments/data_request_2026_08_14/main.py` (`--from-dir`, `--hydrate own_posts|quotes_replies|all`)
- `experiments/data_request_2026_08_14/README.md` (hydrate commands)
- `tests/experiments/test_data_request_2026_08_14_hydrate.py` (create)

### Forbidden to change

- `experiments/aoc_getrepo_derived_stats_2026_08_11/**`
- `experimentation/aoc_posts_getrepo_metrics/**` (import the batch size constant if you want; do not change that package)
- Repo cache format from Step 3
- Activity table shapes from Step 4

## Behavior requirements

Use `create_public_client()`. Do not log in. Do not send `getPosts` through a PDS session.

### Modes

| `--hydrate` | URIs to request, if status is not `ok` |
|---|---|
| `none` | none (Step 5) |
| `own_posts` | `post_uri` values that appear in `original_posts.csv` or `quotes.csv` or `replies.csv` as the member's own post (the activity `post_uri`, not `quoted_post_uri` / `parent_post_uri`) |
| `quotes_replies` | `own_posts`, plus `quoted_post_uri` and `parent_post_uri` |
| `all` | every `posts.csv` URI that is not `ok` |

Never add `reply_root_uri` unless that URI is already a `posts.csv` row.

A URI that is already `ok` is skipped in every mode.

### AppView lookup

Call `client.app.bsky.feed.get_posts({"uris": batch})` in batches of 25 unique URIs.

When AppView returns a post, set `hydration_status="ok"` and fill `post_cid`, `author_did`, `author_handle`, `author_display_name`, `created_at`, `indexed_at`, `text`, `has_image`, `has_video`, `langs` (language codes joined with semicolons), and the five count fields (`like_count`, `reply_count`, `repost_count`, `quote_count`, `save_count` from `bookmarkCount`).

When AppView omits a URI, keep the URI. If repo text exists (`repo_only` before the call), leave it `repo_only` and leave counts null. If the row was `pending`, set `hydration_status="not_found"` and leave other fields null.

When a `get_posts` call raises, mark every URI in that batch `hydration_status="failed"` unless the row was `repo_only` (keep `repo_only` and still append an error). Append fetch-error dicts with `stage="getPosts"` and `uri` set.

Checkpoint: after each successful batch, rewrite `posts.csv` (or a sidecar that the next start reloads) so a crash does not redo finished URIs. Reloading `posts.csv` and skipping `ok` is enough if writes are atomic (write temp file, then replace).

`--from-dir` is required when `hydrate` is not `none`. Load existing CSVs from that folder. Do not call `fetch_member_repos`.

```bash
PYTHONPATH=. uv run python experiments/data_request_2026_08_14/main.py --from-dir experiments/data_request_2026_08_14/data/<timestamp> --hydrate own_posts
PYTHONPATH=. uv run python experiments/data_request_2026_08_14/main.py --from-dir experiments/data_request_2026_08_14/data/<timestamp> --hydrate quotes_replies
PYTHONPATH=. uv run python experiments/data_request_2026_08_14/main.py --from-dir experiments/data_request_2026_08_14/data/<timestamp> --hydrate all
```

## Implement-from-spec phases

### Phase 0. Scope

`select_uris_to_hydrate(posts_rows, activity, mode) -> list[str]`

`hydrate_posts(client, posts_rows, uris) -> tuple[list[dict], list[dict]]`

### Phase 1. Scaffold

Stubs raising `NotImplementedError`. Tests import them.

### Phase 2. Contracts

Mode names match Step 1 constants. Output row keys still match `POSTS_CSV_FIELDNAMES`.

### Phase 3. Test design

1. **Given** one `repo_only` member post and one `pending` like target **when** mode is `own_posts` **then** only the member post URI is requested.
2. **Given** a quote with `quoted_post_uri` pending **when** mode is `quotes_replies` **then** both the quote post and the quoted URI are requested if they are not `ok`.
3. **Given** mode `all` **when** one row is already `ok` **then** that URI is not sent to `get_posts`.
4. **Given** mocked `get_posts` returning one liked URI **when** hydrate **then** that row is `ok` with text and counts, and the like row in `likes.csv` is unchanged.
5. **Given** mocked `get_posts` omitting a pending URI **when** hydrate **then** the row becomes `not_found`.
6. **Given** mocked `get_posts` raising **when** hydrate a pending URI **then** the row is `failed` and an error has `stage="getPosts"`.
7. **Given** 26 unique URIs **when** hydrate **then** `get_posts` is called twice.
8. **Given** `run(from_dir=..., hydrate="all")` **when** executed with mocks **then** `fetch_member_repos` is not called.

### Phase 4. Flesh units of work

1. URI selection by mode, skip `ok`.
2. `getPosts` batching and status updates.
3. Atomic rewrite of `posts.csv` plus metadata `hydrate_mode`.

### Phase 5. Done

Hydrate unit tests green without network.

## Pass / fail

### Must pass

- [ ] `uv run pytest tests/experiments/test_data_request_2026_08_14_hydrate.py -q` is green.
- [ ] Earlier step tests stay green.
- [ ] `own_posts` does not request like-target URIs.
- [ ] Already-`ok` URIs are not requested again.

### Must fail / must not happen

- [ ] Calling getRepo during a `--from-dir` hydrate run.
- [ ] Sending `getPosts` through a logged-in PDS client.
- [ ] Hydrating `reply_root_uri` unless it is already a `posts.csv` row.
- [ ] Changing like, quote, or reply join-key files.

## Commands

```bash
uv run pytest tests/experiments/test_data_request_2026_08_14_hydrate.py tests/experiments/test_data_request_2026_08_14_*.py -q
```

Expected: all pass, no network.

## Done when

An operator can ship `--hydrate none`, then fill counts on member posts, then quote and reply targets, then all remaining URIs, each time resuming from `posts.csv` without re-downloading repos.

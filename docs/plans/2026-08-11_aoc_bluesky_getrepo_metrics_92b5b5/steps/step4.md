# Step 4: Derive metrics, write outputs, add unit tests

## Goal

Join feed post URIs to the getRepo index, derive the frozen CSV columns using only repository record fields (everything else missing / `unknown`), write `posts_metrics.csv` + `metadata.json`, and close the `main.py` path.

## Scope

- **Caller path segment:** `derive_rows` → `write_outputs` → complete `main`
- **Slice:** per-URI metric row → CSV/JSON under `data/<sync_timestamp>/`
- **Out of scope:** AppView engagement endpoints; changing feed/repo contracts; editing `aoc_followers_backfill`

## Files to inspect

- `experimentation/aoc_posts_getrepo_metrics/metrics.py` (stub)
- `experimentation/aoc_posts_getrepo_metrics/output.py` (stub)
- `experimentation/aoc_posts_getrepo_metrics/constants.py` — `CSV_FIELDNAMES`
- `experimentation/aoc_followers_backfill/backfill.py` — `_build_post_row` embed/reply/langs helpers
- `strategy_planning/2026-07-15_getrepo_return_type.md` — post record schema
- `experimentation/aoc_followers_backfill/output.py` — CSV + metadata pattern
- `lib/timestamp_utils.py`

## Files allowed to change

- `experimentation/aoc_posts_getrepo_metrics/metrics.py`
- `experimentation/aoc_posts_getrepo_metrics/output.py`
- `experimentation/aoc_posts_getrepo_metrics/main.py` (fill metadata dict; handle errors if already stubbed)
- **New** `tests/experimentation/aoc_posts_getrepo_metrics/test_metrics.py`
- **New** `tests/experimentation/aoc_posts_getrepo_metrics/test_output.py`
- `experimentation/aoc_posts_getrepo_metrics/README.md` (final run instructions)
- `experimentation/aoc_posts_getrepo_metrics/constants.py` — only if a helper constant is required (e.g. missing sentinel documentation)

## Files forbidden to change

- `experimentation/aoc_followers_backfill/**`
- `experimentation/aoc_posts_getrepo_metrics/feed.py`
- `experimentation/aoc_posts_getrepo_metrics/repo.py`
- `data_platform/**`
- Production sync / jetstream code

## Contracts

### Missing-value rule

Use Python `None` in row dicts. CSV writer must emit empty cells for `None` (not the string `"None"`). Do not call pandas solely to get `NaN`; `None` is sufficient. If a test asserts with pandas, `pd.isna` on read-back empty cells is acceptable.

### `derive_row(post_uri: str, record: dict | None) -> dict`

Always return a dict with exactly the keys in `CSV_FIELDNAMES`.

| Column | Rule |
|--------|------|
| `post_uri` | Input URI |
| `post_rkey` | Final path segment of URI |
| `created_at` | `record["createdAt"]` if record else `None` |
| `deleted` | Always the string `unknown` |
| `deleted_at` | Always `None` |
| `post_type` | If record: `"reply"` when `record` has `reply`, else `"original"`; if no record: `None` |
| `has_image` | If record: `True` when embed `$type` is images, or `recordWithMedia` whose media is images; else `False`. If no record: `None` |
| `has_video` | If record: `True` when embed `$type` is video, or `recordWithMedia` whose media is video; else `False`. If no record: `None` |
| `langs` | If record: `";"`.join(`record.get("langs") or []`); if no record: `None` |
| `like_count` | Always `None` |
| `reply_count` | Always `None` |
| `repost_count` | Always `None` |
| `quote_count` | Always `None` |
| `save_count` | Always `None` |
| `counts_read_at` | Always `None` |

**No additional API calls inside `derive_row` / `derive_rows`.**

Embed `$type` values to treat (suffix or full NSID both OK if normalized consistently):

- Image: `app.bsky.embed.images`
- Video: `app.bsky.embed.video`
- Nested: `app.bsky.embed.recordWithMedia` → inspect nested `media.$type`

### `derive_rows(post_uris, posts_by_uri) -> list[dict]`

Preserve `post_uris` order. For each URI, `derive_row(uri, posts_by_uri.get(uri))`.

### `write_outputs(rows, *, metadata, sync_timestamp) -> Path`

1. Create `experimentation/aoc_posts_getrepo_metrics/data/<sync_timestamp>/`.
2. Write `posts_metrics.csv` with `CSV_FIELDNAMES` header via `csv.DictWriter`.
3. Write `metadata.json` containing at least:
   - `sync_timestamp`
   - `target_handle`
   - `target_did`
   - `min_posts`
   - `post_uri_count`
   - `rows_with_repo_record`
   - `rows_missing_repo_record`
   - `source_listing` = `app.bsky.feed.getAuthorFeed`
   - `source_repo` = `com.atproto.sync.getRepo`
   - `get_repo_calls` = `1`
4. Return the output directory path.

### `main.py` metadata

Populate the metadata fields above from the live run. Print absolute/relative output path and `len(rows)`.

## Test design (TDD)

### `test_metrics.py`

| Test | Assert |
|------|--------|
| `test_derive_row_original_no_media` | `post_type=="original"`, `has_image is False`, `has_video is False`, `deleted=="unknown"` |
| `test_derive_row_reply` | record with `reply` → `post_type=="reply"` |
| `test_derive_row_images_embed` | images embed → `has_image is True` |
| `test_derive_row_video_embed` | video embed → `has_video is True` |
| `test_derive_row_record_with_media_images` | recordWithMedia + images media → `has_image is True` |
| `test_derive_row_missing_record` | `record is None` → `deleted=="unknown"`, engagement cols `None`, `created_at is None`, `post_type is None` |
| `test_derive_row_engagement_always_none` | even with full record, like/reply/repost/quote/save/`counts_read_at` are `None` |
| `test_derive_rows_preserves_order` | URIs `[u2,u1]` stay that order |

### `test_output.py`

| Test | Assert |
|------|--------|
| `test_write_outputs_creates_csv_and_metadata` | temp dir via monkeypatch `OUTPUT_ROOT`; files exist; CSV has header + N rows |
| `test_write_outputs_empty_none_cells` | row with `None` counts → CSV empty fields, not `"None"` |

## Implementation order

1. Write metric tests → implement `derive_row` / `derive_rows`.
2. Write output tests → implement `write_outputs`.
3. Finish `main.py` metadata and README run command.
4. Run full package test suite.

## Must pass

```bash
uv run pytest tests/experimentation/aoc_posts_getrepo_metrics/ -q
```

Expected: all tests pass (exit code 0).

```bash
rg "get_posts|getPosts|get_likes|like_count|search_posts" experimentation/aoc_posts_getrepo_metrics/ -g'!data/**'
```

Expected: no matches that invoke AppView engagement/enrichment APIs (string `like_count` as a **CSV column name** in constants is allowed; calls like `client.app.bsky.feed.get_likes` are forbidden). Prefer:

```bash
rg "get_likes|get_posts|search_posts|getPosts|getLikes" experimentation/aoc_posts_getrepo_metrics/
```

Expected: no matches.

## Must fail

- Setting `deleted` to `yes` / `no` based on missing repo records.
- Populating engagement counts from any source.
- Calling `getRepo` inside the metrics loop.

## Manual live run (optional, operator)

```bash
PYTHONPATH=. uv run python experimentation/aoc_posts_getrepo_metrics/main.py
```

Expected:

- Creates `experimentation/aoc_posts_getrepo_metrics/data/<timestamp>/posts_metrics.csv`
- CSV row count ≥ 50
- Every `deleted` cell is `unknown`
- Engagement count columns empty
- `metadata.json` has `"get_repo_calls": 1`

## Done when

- All offline tests green.
- `main.py` end-to-end path is complete for a live operator run.
- Plan “done” checklist items 1–7 in `plan.md` are satisfied.

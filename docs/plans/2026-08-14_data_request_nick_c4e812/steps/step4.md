# Step 4: Activity tables, posts table, and lookups

Filter actor records to the 365-day window. Build originals, likes, reposts, quotes, and replies as join-key tables. Build `posts.csv` rows for cohort posts in the window and for every like, repost, quote, and reply target. Fill text, media flags, language, author, and counts from AppView `getPosts` when the lookup returns the URI. Write an empty saves table in memory (header columns, zero rows).

## Scope

- **Caller:** `main.run` will call activity and hydrate after repo fetch, then pass tables to Step 5 for graph and disk write.
- **Slice:** pure windowing plus mocked `getPosts`. No filesystem write yet.
- **Out of scope:** `follow_edges.csv`, `follow_actions.csv`, `run_metadata.json`, live network, `main.run` wiring.

## Files

### Inspect

- `experiments/data_request_2026_08_14/EXPECTED_FILES.md` (activity and posts columns)
- `experiments/aoc_getrepo_derived_stats_2026_08_11/records.py` (`filter_rows_by_window`, `created_at_in_window`, `extract_quoted_post_uri` already applied on `PostRow`)
- `experimentation/aoc_posts_getrepo_metrics/constants.py` (`GET_POSTS_MAX_URIS = 25`)
- `experimentation/aoc_posts_getrepo_metrics/enrichment.py` (batch `get_posts` loop; this experiment needs text and media too, so do not reuse `fetch_engagement_by_uri` as-is)
- `experimentation/aoc_posts_getrepo_metrics/metrics.py` (`has_image` / `has_video` from embed type)

### Allowed to change

- `experiments/data_request_2026_08_14/activity.py` (create)
- `experiments/data_request_2026_08_14/hydrate.py` (create)
- `experiments/data_request_2026_08_14/constants.py` (import or copy `GET_POSTS_MAX_URIS = 25`)
- `tests/experiments/test_data_request_2026_08_14_activity.py` (create)
- `tests/experiments/test_data_request_2026_08_14_hydrate.py` (create)

### Forbidden to change

- `experiments/aoc_getrepo_derived_stats_2026_08_11/**`
- `experimentation/aoc_posts_getrepo_metrics/**` (import the batch size constant if you want; do not change that package)
- Follow graph logic (Step 5)
- Output writers (Step 5)

## Behavior requirements

### Window

A record is in the window when `created_at_in_window` is true for `window_start` and `window_end`. Import that helper from `experiments.aoc_getrepo_derived_stats_2026_08_11.records`.

### Activity rows (actor is the cohort member)

| Table | Include when | Columns |
|---|---|---|
| `original_posts` | post in window and `is_reply` is false | `actor_did`, `post_uri` |
| `likes` | like in window | `actor_did`, `like_uri`, `like_created_at`, `post_uri` (subject URI) |
| `reposts` | repost in window | `actor_did`, `repost_uri`, `repost_created_at`, `post_uri` (subject URI) |
| `quotes` | post in window and `quoted_post_uri` is set | `actor_did`, `post_uri`, `quoted_post_uri` |
| `replies` | post in window and `is_reply` is true | `actor_did`, `post_uri`, `parent_post_uri`, `reply_root_uri` |
| `saves` | never | same columns as likes, zero rows |

A quote that is not a reply appears in both `original_posts` and `quotes`.

Skip a like or repost with a missing `subject_uri` (do not invent a join key). Still count that skip only as a dropped row, not as a fetch error.

### Posts table

Union these URIs, then one row per unique URI:

- Cohort posts in the window (the post URI)
- Like and repost subject URIs from windowed likes and reposts
- `quoted_post_uri` from windowed quotes
- `parent_post_uri` from windowed replies

Do not require a row for `reply_root_uri` unless that URI is already in the union for another reason.

For a cohort-authored post in the window, you may fill `text`, `created_at`, `post_type`, and quote or reply pointers from the repo `PostRow` before AppView returns. `post_type` is `reply` when `is_reply` is true, else `original`.

### AppView lookup

Call `client.app.bsky.feed.get_posts({"uris": batch})` in batches of 25 unique URIs.

When AppView returns a post, set `hydration_status="ok"` and fill `post_cid`, `author_did`, `author_handle`, `author_display_name`, `created_at`, `indexed_at`, `text`, `has_image`, `has_video`, `langs` (language codes joined with semicolons), and the five count fields (`like_count`, `reply_count`, `repost_count`, `quote_count`, `save_count` from `bookmarkCount`).

When AppView omits a URI, keep the URI. If repo text exists, set `hydration_status="repo_only"` and leave AppView-only counts null if they were never fetched. If no repo text exists, set `hydration_status="not_found"` and leave other fields null.

When a `get_posts` call raises, mark every URI in that batch `hydration_status="failed"` unless repo text already justified `repo_only`. Append fetch-error dicts with `stage="getPosts"` and `uri` set.

`has_image` is true when the embed type is `app.bsky.embed.images` or a record-with-media whose media is images. `has_video` is true for `app.bsky.embed.video` or record-with-media whose media is video. If both are absent, both flags are false on an `ok` row.

## Implement-from-spec phases

### Phase 0. Scope

`build_activity(bundles, window_start, window_end) -> ActivityTables`

`hydrate_posts(client, activity, bundles) -> tuple[list[dict], list[dict]]` (post rows, getPosts errors)

### Phase 1. Scaffold

Stubs raising `NotImplementedError`. Tests import them.

### Phase 2. Contracts

Activity and posts row keys equal the `schemas.py` tuples.

### Phase 3. Test design

1. **Given** an original, a reply, and a quote in the window, plus an old original **when** `build_activity` **then** originals exclude the reply and the old post, quotes include the quote, and the quote URI is also in originals if it is not a reply.
2. **Given** likes in and out of the window **when** `build_activity` **then** only the like inside the window remains, joined on `subject_uri`.
3. **Given** `build_activity` **when** saves are requested **then** zero save rows and save columns match likes.
4. **Given** mocked `get_posts` returning one liked URI **when** hydrate **then** that `posts.csv` row is `ok` with text and counts, and the like row still has that `post_uri`.
5. **Given** mocked `get_posts` omitting a URI that exists only as a like target **when** hydrate **then** a posts row exists with `hydration_status="not_found"`.
6. **Given** a cohort original in the window and `get_posts` raising **when** hydrate **then** the posts row can be `repo_only` or `failed` with text still present from the repo, and an error has `stage="getPosts"`.
7. **Given** 26 unique URIs **when** hydrate **then** `get_posts` is called twice.

### Phase 4. Flesh units of work

1. Activity tables for the window, including empty saves.
2. URI union for `posts.csv`.
3. `getPosts` batching and `hydration_status`.

### Phase 5. Done

Activity and hydrate tests green without network.

## Pass / fail

### Must pass

- [ ] `uv run pytest tests/experiments/test_data_request_2026_08_14_activity.py tests/experiments/test_data_request_2026_08_14_hydrate.py -q` is green.
- [ ] Earlier step tests stay green.
- [ ] Saves have zero rows.
- [ ] Missing targets keep a posts row.

### Must fail / must not happen

- [ ] Copying full post text onto every like or quote row.
- [ ] Hydrating `reply_root_uri` unless it is already required for another reason.
- [ ] Inventing save rows.
- [ ] Writing files before Step 5.

## Commands

```bash
uv run pytest tests/experiments/test_data_request_2026_08_14_activity.py tests/experiments/test_data_request_2026_08_14_hydrate.py tests/experiments/test_data_request_2026_08_14_fetch.py tests/experiments/test_data_request_2026_08_14_profiles.py tests/experiments/test_data_request_2026_08_14_contracts.py -q
```

Expected: all pass, no network.

## Done when

Activity tables and posts rows exist in memory, saves are empty, and lookups are covered by mocks. Ready for Step 5 follows, write, and smoke.

# Step 4: Activity tables and posts rows from the repo cache

Filter actor records to the 365-day window. Build originals, likes, reposts, quotes, and replies as join-key tables. Build `posts.csv` rows for member-authored posts in the window and for every like, repost, quote, and reply-parent URI. Do not call AppView `getPosts`. Member-authored posts are `hydration_status=repo_only` with text from the repo. Other URIs are `hydration_status=pending` with null bodies and counts. Write an empty saves table in memory (header columns, zero rows).

## Scope

- **Caller:** `main.run` will call activity after repo fetch, then pass tables to Step 5 for graph and disk write.
- **Slice:** pure windowing and URI union. No filesystem write yet. No `getPosts`.
- **Out of scope:** `follow_edges.csv`, `follow_actions.csv`, `run_metadata.json`, live network, `main.run` wiring, AppView post lookup (Step 6).

## Files

### Inspect

- `experiments/data_request_2026_08_14/EXPECTED_FILES.md` (activity and posts columns)
- `experiments/aoc_getrepo_derived_stats_2026_08_11/records.py` (`filter_rows_by_window`, `created_at_in_window`, `extract_quoted_post_uri` already applied on `PostRow`)
- `experimentation/aoc_posts_getrepo_metrics/metrics.py` (`has_image` / `has_video` from embed type, for member posts only)

### Allowed to change

- `experiments/data_request_2026_08_14/activity.py` (create)
- `tests/experiments/test_data_request_2026_08_14_activity.py` (create)

### Forbidden to change

- `experiments/aoc_getrepo_derived_stats_2026_08_11/**`
- Follow graph logic (Step 5)
- Output writers (Step 5)
- Adding `hydrate.py` in this step

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

### Posts table (no AppView)

Union these URIs, then one row per unique URI:

- Cohort posts in the window (the post URI)
- Like and repost subject URIs from windowed likes and reposts
- `quoted_post_uri` from windowed quotes
- `parent_post_uri` from windowed replies

Do not require a row for `reply_root_uri` unless that URI is already in the union for another reason.

For a cohort-authored post in the window, fill `text`, `created_at`, `author_did`, `post_type`, langs, and media flags from the repo `PostRow`. `post_type` is `reply` when `is_reply` is true, else `original`. Set `hydration_status=repo_only`. Leave AppView count fields null.

For every other URI in the union, emit a row with `post_uri` set, other fields null, and `hydration_status=pending`.

`has_image` is true when the embed type is `app.bsky.embed.images` or a record-with-media whose media is images. `has_video` is true for `app.bsky.embed.video` or record-with-media whose media is video. If both are absent on a `repo_only` row, both flags are false.

## Implement-from-spec phases

### Phase 0. Scope

`build_activity(bundles, window_start, window_end) -> ActivityTables` including `posts` rows.

### Phase 1. Scaffold

Stub raising `NotImplementedError`. Tests import it.

### Phase 2. Contracts

Activity and posts row keys equal the `schemas.py` tuples.

### Phase 3. Test design

1. **Given** an original, a reply, and a quote in the window, plus an old original **when** `build_activity` **then** originals exclude the reply and the old post, quotes include the quote, and the quote URI is also in originals if it is not a reply.
2. **Given** likes in and out of the window **when** `build_activity` **then** only the like inside the window remains, joined on `subject_uri`.
3. **Given** `build_activity` **when** saves are requested **then** zero save rows and save columns match likes.
4. **Given** a cohort original in the window **when** `build_activity` **then** `posts.csv` has that URI with `hydration_status=repo_only` and non-null text.
5. **Given** a like whose subject is not a cohort post **when** `build_activity` **then** `posts.csv` has that URI with `hydration_status=pending` and null text.
6. **Given** activity source **when** inspected **then** it does not call `get_posts` or import a hydrate module.

### Phase 4. Flesh units of work

1. Activity tables for the window, including empty saves.
2. URI union and `repo_only` vs `pending` posts rows.

### Phase 5. Done

Activity tests green without network.

## Pass / fail

### Must pass

- [ ] `uv run pytest tests/experiments/test_data_request_2026_08_14_activity.py -q` is green.
- [ ] Earlier step tests stay green.
- [ ] Saves have zero rows.
- [ ] Like targets keep a `pending` posts row.

### Must fail / must not happen

- [ ] Copying full post text onto every like or quote row.
- [ ] Adding a `reply_root_uri` posts row unless that URI is already required for another reason.
- [ ] Inventing save rows.
- [ ] Calling `getPosts` in this step.
- [ ] Writing files before Step 5.

## Commands

```bash
uv run pytest tests/experiments/test_data_request_2026_08_14_activity.py tests/experiments/test_data_request_2026_08_14_fetch.py tests/experiments/test_data_request_2026_08_14_profiles.py tests/experiments/test_data_request_2026_08_14_contracts.py -q
```

Expected: all pass, no network.

## Done when

Activity tables and posts rows exist in memory, saves are empty, member posts are `repo_only`, and other URIs are `pending`. Ready for Step 5 follows, write, and smoke.

# Step 5: Follows, write the first folder, and smoke

Build current follow edges where both ends are in the member list. Build follow actions during the window that still exist (the followed DID may be outside the list). Write every generated file from `EXPECTED_FILES.md` under a timestamped folder with `--hydrate none`. Wire `--profiles-only` so profiles can ship without getRepo. Smoke a small DID subset before anyone runs all 8,431.

## Scope

- **Caller:** `experiments/data_request_2026_08_14/main.py` → `run()`.
- **Slice:** graph tables, filesystem write, metadata, CLI flags, README, gitignore for `data/` and `cache/`.
- **Out of scope:** Unfollow history, inventing private saves, changing shared getRepo decode, AppView `getPosts` (Step 6).

## Files

### Inspect

- `experiments/data_request_2026_08_14/EXPECTED_FILES.md` (`follow_edges.csv`, `follow_actions.csv`, `fetch_errors.csv`, `run_metadata.json`)
- `experiments/aoc_getrepo_derived_stats_2026_08_11/output.py` (timestamp folder pattern)
- `experiments/aoc_getrepo_derived_stats_2026_08_11/main.py` (client creation and loop)
- `experiments/aoc_getrepo_derived_stats_2026_08_11/derive.py` (cohort follow cross-links, reuse the idea, not the derived-stats document)
- `.gitignore` (how other experiment `data/` dirs are ignored)

### Allowed to change

- `experiments/data_request_2026_08_14/graph.py` (create)
- `experiments/data_request_2026_08_14/output.py` (create)
- `experiments/data_request_2026_08_14/main.py` (implement `run()`)
- `experiments/data_request_2026_08_14/README.md`
- `tests/experiments/test_data_request_2026_08_14_graph.py` (create)
- `tests/experiments/test_data_request_2026_08_14_main.py` (create, fully mocked end to end)
- `.gitignore` (add `experiments/data_request_2026_08_14/data/` and `experiments/data_request_2026_08_14/cache/`)

### Forbidden to change

- `experimentation/aoc_followers_backfill/**` source (imports only)
- `experiments/aoc_getrepo_derived_stats_2026_08_11/**` source (imports only)
- `data_platform/**`

## Behavior requirements

### Follow edges

For every follow record that still exists on a successful bundle, if `followed_did` is also in the member list, emit one `follow_edges.csv` row:

- `follower_did` = bundle DID
- `followee_did` = `followed_did`
- `follow_uri` = follow record URI
- `follow_created_at` = follow `createdAt` (may be before the window)

Do not window-filter this file. It is the graph at run time.

### Follow actions

For every still-present follow whose `createdAt` is in the window, emit one `follow_actions.csv` row:

- `actor_did` = bundle DID
- `follow_uri`, `followed_did`, `created_at`
- `followed_in_cohort` true when `followed_did` is in the member list

The followed account does not need to be in the cohort.

### Write

Capture `run_start` once in UTC. `window_end = run_start`. `window_start = run_start - 365 days`.

Create `experiments/data_request_2026_08_14/data/<run_timestamp>/` using the same `YYYY_MM_DD-HH:MM:SS` stamp and suffix-on-collision pattern as `experiments/aoc_getrepo_derived_stats_2026_08_11/output.py`.

`--profiles-only` writes `profiles.csv`, `fetch_errors.csv` (profile errors only), and `run_metadata.json`. It does not call getRepo.

`--hydrate none` (default) writes all generated files named in `EXPECTED_FILES.md`. `saves.csv` is header plus zero data rows. Concatenate profile errors and repo errors into `fetch_errors.csv`. There are no getPosts errors yet.

`run_metadata.json` includes `run_timestamp`, `window_start`, `window_end`, `cohort_size` (member rows actually processed), `record_counts`, `source_methods` (AppView profiles, relay getRepo, imported decode), `hydrate_mode` (`none` or omitted for profiles-only), and `unavailable_fields` listing saved posts, unfollows, deletions, and (for `--hydrate none`) pending target bodies and engagement counts.

### Entrypoint

```bash
PYTHONPATH=. uv run python experiments/data_request_2026_08_14/main.py --limit 3 --profiles-only
PYTHONPATH=. uv run python experiments/data_request_2026_08_14/main.py --limit 3 --hydrate none
PYTHONPATH=. uv run python experiments/data_request_2026_08_14/main.py --hydrate none
```

`--hydrate none` loads members, optionally keeps the first `limit` members, then profiles → cached repos → activity → graph → write. Print member count, cache hits, successful fetches, failed repos, and output path.

Sequential `getRepo` is acceptable. Do not add a worker pool in this step.

## Implement-from-spec phases

### Phase 0. Scope

Caller is `main.run` happy path for profiles-only and hydrate none.

### Phase 1. Scaffold

`graph.build_follow_tables(...)` stub, `output.write_outputs(...)` stub, `main.run` still a stub.

### Phase 2. Contracts

Follow column names, output file names, and `hydrate_mode=none` metadata frozen by tests.

### Phase 3. Test design (mocked)

1. **Given** member A follows member B, and B follows outsider C **when** graph **then** `follow_edges` has only A→B, and `follow_actions` includes A→B and B→C with `followed_in_cohort` true then false.
2. **Given** a follow created before the window **when** graph **then** it appears in `follow_edges` if both ends are members, and it does not appear in `follow_actions`.
3. **Given** mocked load and profiles **when** `run(profiles_only=True, limit=2)` **then** the output dir has `profiles.csv` with 2 rows, has `run_metadata.json`, and does not call `fetch_member_repos`.
4. **Given** mocked load, profiles, fetch, activity, and graph **when** `run(limit=2, hydrate="none")` **then** the output dir contains every generated file, `saves.csv` has only a header, there is no unfollows file, and `posts.csv` rows that are not member-authored are `pending`.
5. **Given** one repo error **when** write **then** `fetch_errors.csv` has that row and `run_metadata.json` `hydrate_mode` is `none`.

### Phase 4. Flesh units of work

1. Follow edge and follow action tables.
2. `write_outputs`.
3. `main.run` wiring, `--limit`, `--profiles-only`, `--hydrate none`, README.

### Phase 5. Done

Offline tests green, then a live smoke with `--limit 3 --hydrate none`.

## Pass / fail

### Must pass (offline)

- [ ] `uv run pytest tests/experiments/test_data_request_2026_08_14_*.py -q` all green (Step 6 tests may not exist yet).
- [ ] No network in pytest.
- [ ] `.gitignore` includes `experiments/data_request_2026_08_14/data/` and `experiments/data_request_2026_08_14/cache/`.

### Must pass (live smoke)

```bash
PYTHONPATH=. uv run python experiments/data_request_2026_08_14/main.py --limit 3 --hydrate none
```

Expected stdout includes a processed count of 3, cache-hit or fetch counts, and an output path under `experiments/data_request_2026_08_14/data/`.

After the smoke, the output folder contains `profiles.csv`, `posts.csv`, `original_posts.csv`, `likes.csv`, `reposts.csv`, `quotes.csv`, `replies.csv`, `saves.csv`, `follow_edges.csv`, `follow_actions.csv`, `fetch_errors.csv`, and `run_metadata.json`. `saves.csv` has a header and no data rows. `profiles.csv` has 3 rows. Activity rows join to `posts.csv` on `post_uri`. Member posts are `repo_only`. Other URIs are `pending`.

Do not run the full 8,431 until the smoke folder looks correct. The full `--hydrate none` run may take 2 to 10 hours of getRepo. Resume from `cache/repos/` if it stops.

### Must fail / must not happen

- [ ] Generating unfollows or post deletions.
- [ ] Writing save rows with invented bookmark records.
- [ ] Copying decode code instead of importing `fetch_one_repo`.
- [ ] Calling `getPosts` in this step.
- [ ] Changing `data_platform/**`.

## Commands

```bash
uv run pytest tests/experiments/test_data_request_2026_08_14_graph.py tests/experiments/test_data_request_2026_08_14_main.py tests/experiments/test_data_request_2026_08_14_activity.py tests/experiments/test_data_request_2026_08_14_fetch.py tests/experiments/test_data_request_2026_08_14_profiles.py tests/experiments/test_data_request_2026_08_14_contracts.py -q
```

Expected: all pass, no network.

```bash
PYTHONPATH=. uv run python experiments/data_request_2026_08_14/main.py --limit 3 --hydrate none
```

Expected: a new folder under `experiments/data_request_2026_08_14/data/` with every generated file from `EXPECTED_FILES.md` and no AppView post lookup.

## Done when

Offline tests are green, smoke with three DIDs writes a complete `--hydrate none` folder, `--profiles-only` works, and an operator can run the full list with `--hydrate none` and resume from the repo cache.

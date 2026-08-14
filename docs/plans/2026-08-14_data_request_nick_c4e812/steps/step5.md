# Step 5: Follows, write outputs, and smoke

Build current follow edges where both ends are in the member list. Build follow actions during the window that still exist (the followed DID may be outside the list). Write every generated file from `EXPECTED_FILES.md` under a timestamped folder. Wire `main.run`. Smoke a small DID subset before anyone runs all 8,431.

## Scope

- **Caller:** `experiments/data_request_2026_08_14/main.py` → `run()`.
- **Slice:** graph tables, filesystem write, metadata, CLI limit for smoke, README, gitignore for `data/`.
- **Out of scope:** Unfollow history, inventing private saves, changing shared getRepo decode.

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
- `.gitignore` (add `experiments/data_request_2026_08_14/data/` only)

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

Write all generated files named in `EXPECTED_FILES.md`. `saves.csv` is header plus zero data rows. Concatenate profile errors, repo errors, and getPosts errors into `fetch_errors.csv`.

`run_metadata.json` includes `run_timestamp`, `window_start`, `window_end`, `cohort_size` (member rows actually processed), `record_counts` (row counts per CSV), `source_methods` (AppView profiles, relay getRepo, imported decode, AppView getPosts), and `unavailable_fields` listing saved posts, unfollows, and deletions.

### Entrypoint

`run(limit: int | None = None)` loads members, optionally keeps the first `limit` members, then profiles → repos → activity → hydrate → graph → write. Print a short stdout summary: member count, successful repos, failed repos, output path.

```bash
PYTHONPATH=. uv run python experiments/data_request_2026_08_14/main.py --limit 3
```

```bash
PYTHONPATH=. uv run python experiments/data_request_2026_08_14/main.py
```

Sequential `getRepo` is acceptable. Do not add a worker pool in this experiment.

## Implement-from-spec phases

### Phase 0. Scope

Caller is `main.run` happy path.

### Phase 1. Scaffold

`graph.build_follow_tables(...)` stub, `output.write_outputs(...)` stub, `main.run` still a stub.

### Phase 2. Contracts

Follow column names and output file names frozen by tests.

### Phase 3. Test design (mocked)

1. **Given** member A follows member B, and B follows outsider C **when** graph **then** `follow_edges` has only A→B, and `follow_actions` includes A→B and B→C with `followed_in_cohort` true then false.
2. **Given** a follow created before the window **when** graph **then** it appears in `follow_edges` if both ends are members, and it does not appear in `follow_actions`.
3. **Given** mocked load, profiles, fetch, activity, hydrate, and graph **when** `run(limit=2)` **then** the output dir contains every generated file, `saves.csv` has only a header, and there is no unfollows file.
4. **Given** one repo error and one getPosts error **when** write **then** `fetch_errors.csv` has both rows and `run_metadata.json` has `unavailable_fields` that include saved posts and unfollows.

### Phase 4. Flesh units of work

1. Follow edge and follow action tables.
2. `write_outputs`.
3. `main.run` wiring, `--limit`, README.

### Phase 5. Done

Offline tests green, then a live smoke with `--limit 3`.

## Pass / fail

### Must pass (offline)

- [ ] `uv run pytest tests/experiments/test_data_request_2026_08_14_*.py -q` all green.
- [ ] No network in pytest.
- [ ] `.gitignore` includes `experiments/data_request_2026_08_14/data/`.

### Must pass (live smoke)

```bash
PYTHONPATH=. uv run python experiments/data_request_2026_08_14/main.py --limit 3
```

Expected stdout includes a processed count of 3, a success/fail repo split, and an output path under `experiments/data_request_2026_08_14/data/`.

After the smoke, the output folder contains `profiles.csv`, `posts.csv`, `original_posts.csv`, `likes.csv`, `reposts.csv`, `quotes.csv`, `replies.csv`, `saves.csv`, `follow_edges.csv`, `follow_actions.csv`, `fetch_errors.csv`, and `run_metadata.json`. `saves.csv` has a header and no data rows. `profiles.csv` has 3 rows (or fewer only if member load was limited incorrectly, which is a fail). Activity rows join to `posts.csv` on `post_uri`.

Do not run the full 8,431 until the smoke folder looks correct.

### Must fail / must not happen

- [ ] Generating unfollows or post deletions.
- [ ] Writing save rows with invented bookmark records.
- [ ] Copying decode code instead of importing `fetch_one_repo`.
- [ ] Changing `data_platform/**`.

## Commands

```bash
uv run pytest tests/experiments/test_data_request_2026_08_14_*.py -q
```

Expected: all pass, no network.

```bash
PYTHONPATH=. uv run python experiments/data_request_2026_08_14/main.py --limit 3
```

Expected: a new folder under `experiments/data_request_2026_08_14/data/` with every generated file from `EXPECTED_FILES.md`.

## Done when

Offline tests are green, smoke with three DIDs writes a complete folder, and an operator can run the full list with the same entrypoint and no `--limit`.

# Step 1: Freeze window, cohort, and output contracts

Freeze contracts before behavior. Scaffold the experiment package and write failing tests that encode `experiments/data_request_2026_08_14/EXPECTED_FILES.md`. Do not call AppView, the relay, or `getRepo` yet.

## Scope

- **Caller (for later steps):** `experiments/data_request_2026_08_14/main.py` → `run()` will load members, fetch profiles, fetch repos, build tables, and write a timestamped folder.
- **Slice:** Constants, CSV column tuples, member-list loader, a stub `run()`, and failing contract tests.
- **Out of scope:** Live AppView or relay calls, CAR decode, writing real CSVs from network data.

## Files

### Inspect

- `experiments/data_request_2026_08_14/EXPECTED_FILES.md`
- `experiments/data_request_2026_08_14/REQUEST_DETAILS.md`
- `experiments/data_request_2026_08_14/greedy10_dedup_members.csv` (header `did,n_pools,seeds`; 8,431 data rows)
- `experiments/aoc_getrepo_derived_stats_2026_08_11/constants.py`
- `experiments/aoc_getrepo_derived_stats_2026_08_11/main.py`
- `experimentation/aoc_followers_backfill/date_window_experiment.py` (pattern for a days-back constant. The AOC file uses 182 for 6 months. The Nick extract uses 365 for 12 months.)

### Allowed to change

- `experiments/data_request_2026_08_14/__init__.py` (create, empty)
- `experiments/data_request_2026_08_14/constants.py` (create)
- `experiments/data_request_2026_08_14/schemas.py` (create)
- `experiments/data_request_2026_08_14/members.py` (create)
- `experiments/data_request_2026_08_14/main.py` (create, stub `run()` only)
- `tests/experiments/test_data_request_2026_08_14_contracts.py` (create)

### Forbidden to change

- `experiments/aoc_getrepo_derived_stats_2026_08_11/**` (import later, do not edit)
- `experimentation/aoc_followers_backfill/**`
- `data_platform/**`
- `pyproject.toml`
- `experiments/data_request_2026_08_14/greedy10_dedup_members.csv`
- `experiments/data_request_2026_08_14/EXPECTED_FILES.md` (read-only contract)

## Contracts to freeze

### Window and input

| Constant | Value |
|---|---|
| Input path | `experiments/data_request_2026_08_14/greedy10_dedup_members.csv` |
| Expected member count | `8431` |
| Window length | `365` days ending at run start (UTC) |
| Window start | inclusive |
| Window end | run-start timestamp |
| Output root | `experiments/data_request_2026_08_14/data/<run_timestamp>/` |

### Generated files (exact names)

`profiles.csv`, `posts.csv`, `original_posts.csv`, `likes.csv`, `reposts.csv`, `quotes.csv`, `replies.csv`, `saves.csv`, `follow_edges.csv`, `follow_actions.csv`, `fetch_errors.csv`, `run_metadata.json`.

Do not generate an unfollows file.

### CSV column order

Copy column names and order from the tables in `EXPECTED_FILES.md` into named tuples in `schemas.py`. Tests compare those tuples to the headers a writer would emit.

### Member row

`load_members(path)` returns one object per CSV row with `did`, `n_pools`, and `seeds`. `n_pools` is an int. Duplicate DIDs in the input are a hard error.

### Stub run

`main.run()` raises `NotImplementedError` until Step 5.

## Implement-from-spec phases

### Phase 0. Scope

Caller is `main.run`, wired in Step 5. File tree:

```text
experiments/data_request_2026_08_14/
  __init__.py
  constants.py
  schemas.py
  members.py
  main.py
tests/experiments/test_data_request_2026_08_14_contracts.py
```

### Phase 1. Scaffold

Create modules so imports resolve. Stub constants, column tuples, `load_members`, and `main.run()` raising `NotImplementedError`.

### Phase 2. Contracts

Lock file names, column order, window length, and member count to `EXPECTED_FILES.md`. Stop if a helper contradicts that doc.

### Phase 3. Test design (failing)

In `tests/experiments/test_data_request_2026_08_14_contracts.py`:

1. **Given** constants **when** imported **then** days back is 365 and expected member count is 8431.
2. **Given** each CSV fieldname tuple in `schemas.py` **when** listed **then** names and order match `EXPECTED_FILES.md`.
3. **Given** a tiny CSV with two member rows **when** `load_members` **then** two objects with `did`, int `n_pools`, and `seeds`.
4. **Given** a CSV with a duplicate DID **when** `load_members` **then** it raises.
5. **Given** generated file name list **when** listed **then** it includes `saves.csv` and does not include an unfollows file.

### Phase 4 to 5

Fill constants, schema tuples, and `load_members` until contract tests are green. No network. `main.run` may stay `NotImplementedError`.

## Pass / fail

### Must pass

- [ ] Package and contract test file exist at the paths above.
- [ ] `uv run pytest tests/experiments/test_data_request_2026_08_14_contracts.py -q` is green.
- [ ] No edits under `experiments/aoc_getrepo_derived_stats_2026_08_11/` or `experimentation/aoc_followers_backfill/`.
- [ ] No live API calls in the new modules.

### Must fail / must not happen

- [ ] Implementing profile fetch or `getRepo` before Step 2 and Step 3.
- [ ] Adding an unfollows output file.
- [ ] Inferring `account_created_at` from post timestamps in schema helpers.

## Commands

```bash
uv run pytest tests/experiments/test_data_request_2026_08_14_contracts.py -q
```

Expected: all contract tests pass after schema helpers are filled. Import errors mean the scaffold is incomplete.

## Done when

Constants, CSV headers, member loading, and the generated file list are locked by tests. Ready for Step 2 profile fetch against these seams.

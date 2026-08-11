# Step 5: Orchestrate, write outputs, and verify live smoke

Wire discovery → repo fetch → derive → timestamped write under `experiments/aoc_getrepo_derived_stats_2026_08_11/data/`. Finish with offline integration tests and one live smoke run against AOC + 50 followers (51 repos).

## Scope

- **Caller:** `experiments/aoc_getrepo_derived_stats_2026_08_11/main.py` → `run()`.
- **Slice:** end-to-end orchestration, filesystem outputs, metadata, smoke verification checklist.
- **Out of scope:** Jetstream/unfollow history; post body hydration; changing shared backfill defaults.

## Files

### Inspect

- `experiments/aoc_getrepo_derived_stats_2026_08_11/discovery.py`
- `experiments/aoc_getrepo_derived_stats_2026_08_11/fetch_repos.py`
- `experiments/aoc_getrepo_derived_stats_2026_08_11/derive.py`
- `experiments/aoc_getrepo_derived_stats_2026_08_11/schemas.py`
- `experimentation/aoc_followers_backfill/output.py` — timestamp folder pattern
- `experiments/reddit_fetch_data_2026_05_23/main.py` — experiment entrypoint style
- `lib/timestamp_utils.py` — if the repo standard sync timestamp helper should be reused

### Allowed to change

- `experiments/aoc_getrepo_derived_stats_2026_08_11/main.py` — implement `run()`
- `experiments/aoc_getrepo_derived_stats_2026_08_11/output.py` — **create**
- `experiments/aoc_getrepo_derived_stats_2026_08_11/README.md` — **create** (how to run + null policy summary)
- `tests/experiments/test_aoc_getrepo_derived_stats_main.py` — **create** (fully mocked e2e)
- `.gitignore` — only if experiment `data/` needs an ignore rule and is not already covered

### Forbidden to change

- `experimentation/aoc_followers_backfill/**` source (imports only)
- `data_platform/**`
- Production ingestion configs

## Behavior requirements

1. Capture `run_start` once in UTC; `window_end = run_start`; `window_start = run_start - 182 days`.
2. `create_public_client()` → `discover_cohort` → `create_relay_client()` → `fetch_cohort_repos` → `derive_stats` → `write_outputs`.
3. Write under `experiments/aoc_getrepo_derived_stats_2026_08_11/data/<run_timestamp>/`:
   - `metadata.json`
   - `derived_stats.json`
   - `derived_stats.csv` (scalars; list fields as JSON strings)
   - `raw/posts.csv`, `raw/likes.csv`, `raw/reposts.csv`, `raw/follows.csv`
4. `metadata.json` must include: window, cohort size requested/actual, per-DID errors, `source_methods` (`appview_discovery`, `appview_followers_count`, `relay_getRepo`, `mst_decode_import`), and note that saves/unfollows/quote-parent bodies are unavailable.
5. Print a short stdout summary: cohort size, successful repos, failed repos, output path.
6. Live smoke may take substantial wall time (51 full-repo downloads). Sequential fetch is acceptable (match existing backfill style).

## Implement-from-spec phases

### Phase 0

Caller = `main.run` happy path.

### Phase 1 — Scaffold

`output.write_outputs(...)` stub; `main.run` still thin.

### Phase 2 — Contracts

Metadata keys and file names frozen by tests.

### Phase 3 — Test design (mocked e2e)

1. **Given** mocked discover returning 3 members (AOC+2) and mocked fetch/derive **when** `run` **then** output dir contains all expected files.
2. **Given** one fetch error **when** `run` **then** metadata `errors` non-empty and `derived_stats.json` still includes that DID with null policy.
3. **Given** derived objects **when** CSV written **then** `saved_posts` / `unfollow_actions` columns are empty/NA, not `[]` mis-encoded as empty list meaning “known empty.”

### Phase 4 — Flesh UoWs

1. `write_outputs` raw CSVs + derived JSON/CSV + metadata.
2. `main.run` wiring.
3. README with exact run command.

### Phase 5

Offline tests green; then live smoke.

## Pass / fail

### Must pass (offline)

- [ ] `uv run pytest tests/experiments/test_aoc_getrepo_derived_stats_*.py -q` all green.
- [ ] No network in pytest.

### Must pass (live smoke)

```bash
PYTHONPATH=. uv run python experiments/aoc_getrepo_derived_stats_2026_08_11/main.py
```

Expected stdout includes successful completion and an output directory path.

Then verify:

```bash
OUT=$(ls -td experiments/aoc_getrepo_derived_stats_2026_08_11/data/*/ | head -1)
test -f "$OUT/metadata.json"
test -f "$OUT/derived_stats.json"
test -f "$OUT/derived_stats.csv"
test -f "$OUT/raw/posts.csv"
python - <<'PY'
import json, sys
from pathlib import Path
out = Path(sys.argv[1])
meta = json.loads((out/"metadata.json").read_text())
stats = json.loads((out/"derived_stats.json").read_text())
assert meta["users_requested_followers"] == 50
assert meta["cohort_size_expected_max"] == 51
assert len(stats) >= 1
for row in stats:
    assert row["saved_posts"] is None
    assert row["unfollow_actions"] is None
    for q in row.get("quoted_posts") or []:
        assert q["quoted_post_body"] is None
    for r in row.get("replied_posts") or []:
        assert r["parent_post_body"] is None
print("smoke ok", len(stats), "members")
PY
"$OUT"
```

Expected: prints `smoke ok <n> members` with `n` equal to discovered cohort size (≤ 51).

### Must fail / must not happen

- [ ] Committing large raw CAR binaries or huge accidental artifacts (CSV/JSON outputs under `data/` should stay gitignored or uncommitted unless explicitly requested).
- [ ] Calling `getPosts` during live run.
- [ ] Non-null `saved_posts` or `unfollow_actions` in outputs.

## Commands

Offline:

```bash
uv run pytest tests/experiments/test_aoc_getrepo_derived_stats_contracts.py \
  tests/experiments/test_aoc_getrepo_derived_stats_discovery.py \
  tests/experiments/test_aoc_getrepo_derived_stats_fetch.py \
  tests/experiments/test_aoc_getrepo_derived_stats_derive.py \
  tests/experiments/test_aoc_getrepo_derived_stats_main.py -q
```

Expected: all pass.

Live:

```bash
PYTHONPATH=. uv run python experiments/aoc_getrepo_derived_stats_2026_08_11/main.py
```

Expected: completes; writes timestamped folder; smoke assertions above succeed.

## Done when

Offline suite is green, live smoke produced ≤51 derived-stat objects with mandatory nulls intact, and README documents how to re-run. Plan implementation package is complete.

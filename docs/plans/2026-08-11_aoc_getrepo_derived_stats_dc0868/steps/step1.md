# Step 1: Freeze cohort rules, window, and derived-stat contracts

Freeze contracts before behavior. Scaffold the experiment package and write failing tests that encode the decisions in [../plan.md](../plan.md). Do not implement discovery, `getRepo` fetch, or derivation logic yet.

## Scope

- **Caller (for later steps):** `experiments/aoc_getrepo_derived_stats_2026_08_11/main.py` → `run()` orchestrates discovery → fetch → derive → write.
- **This slice:** Constants, output path layout, derived-stat field schema, null sentinels, and failing contract tests.
- **Out of scope:** Live AppView / relay calls; CAR decode; writing real CSVs from network data.

## Files

### Inspect

- `docs/plans/2026-08-11_aoc_getrepo_derived_stats_dc0868/plan.md` — resolved decisions and availability matrix
- `experimentation/aoc_followers_backfill/constants.py` — existing collection map and CSV fieldnames (reuse shapes where sensible; do not edit)
- `experimentation/aoc_followers_backfill/date_window_experiment.py` — `SIX_MONTHS_DAYS_BACK = 182`
- `experimentation/aoc_followers_backfill/output.py` — timestamped folder + `metadata.json` pattern
- `experiments/reddit_fetch_data_2026_05_23/main.py` — experiment package layout under `experiments/`
- `strategy_planning/2026-07-15_getrepo_return_type.md` — record field inventory

### Allowed to change

- `experiments/aoc_getrepo_derived_stats_2026_08_11/__init__.py` — **create** (empty)
- `experiments/aoc_getrepo_derived_stats_2026_08_11/constants.py` — **create**
- `experiments/aoc_getrepo_derived_stats_2026_08_11/schemas.py` — **create** (derived-stat field names, null sentinel helpers)
- `experiments/aoc_getrepo_derived_stats_2026_08_11/main.py` — **create** thin stub `run()` / `if __name__` only
- `tests/experiments/test_aoc_getrepo_derived_stats_contracts.py` — **create**

### Forbidden to change

- `experimentation/aoc_followers_backfill/**` (read-only import target for later steps)
- `data_platform/**`
- `pyproject.toml` (no new deps this step; `atproto` and `pandas` already present)
- Any live data under `experimentation/aoc_followers_backfill/data/`

## Contracts to freeze

### Cohort and window

| Constant | Value |
|---|---|
| Target handle | `aoc.bsky.social` |
| Follower sample size | `50` (most recent, AppView newest-first) |
| Cohort size | `51` (AOC + 50 followers) |
| Window length | `182` days trailing from run start |
| Window end | run-start UTC timestamp |

### Null policy

- Missing / unavailable scalar → Python `None` in dicts; when written through pandas, use `pd.NA` / NaN consistently in the derived-stats table.
- Missing list field → empty list `[]` only when the field is *known empty* (e.g. zero original posts in window). Use `None` when the field is *unknowable* (saved posts, unfollows).
- Never invent account creation from earliest post.

### Derived-stats document (one object per cohort member)

Exact top-level keys (stable order):

1. `did`
2. `handle`
3. `display_name`
4. `bio`
5. `account_created_at`
6. `window_start`
7. `window_end`
8. `original_posts` — list of objects `{uri, created_at, text}`
9. `liked_posts` — list of objects `{uri, created_at, subject_uri, subject_cid}`
10. `reposted_posts` — list of objects `{uri, created_at, subject_uri, subject_cid}`
11. `quoted_posts` — list of objects `{uri, created_at, text, quoted_post_uri, quoted_post_body}` where `quoted_post_body` is always `None`
12. `replied_posts` — list of objects `{uri, created_at, text, reply_parent_uri, reply_root_uri, parent_post_body}` where `parent_post_body` is always `None`
13. `saved_posts` — always `None`
14. `cohort_followers` — list of DIDs
15. `cohort_followees` — list of DIDs
16. `followers_count` — AppView scalar or `None`
17. `followees_count` — int count of still-present outbound follows, or `None` if repo missing
18. `follow_actions` — list of objects `{uri, created_at, followed_did}` with `created_at` inside window
19. `unfollow_actions` — always `None`

### Output layout

Under `experiments/aoc_getrepo_derived_stats_2026_08_11/data/<run_timestamp>/`:

| Artifact | Purpose |
|---|---|
| `metadata.json` | run timestamp, window, cohort DIDs/handles, errors, source methods |
| `derived_stats.json` | list of 51 derived-stat objects (or fewer if some repos failed; failed members still appear with nulls + error noted in metadata) |
| `derived_stats.csv` | flattened scalars only (lists serialized as JSON strings or omitted per `schemas.py` decision locked in tests) |
| `raw/posts.csv`, `raw/likes.csv`, `raw/reposts.csv`, `raw/follows.csv` | audit dumps (schemas aligned with existing backfill fieldnames where possible) |

### Source methods (metadata)

- Discovery / scalar followers: AppView public client (`https://public.api.bsky.app`)
- Repos: relay `com.atproto.sync.getRepo` (`https://bsky.network`)
- Decode: import `experimentation.aoc_followers_backfill.mst.decode_repo`

## Implement-from-spec phases for this step

### Phase 0 — Scope

Caller = `main.run` (wired in Step 5). File tree:

```text
experiments/aoc_getrepo_derived_stats_2026_08_11/
  __init__.py
  constants.py
  schemas.py
  main.py
tests/experiments/test_aoc_getrepo_derived_stats_contracts.py
```

### Phase 1 — Scaffold

Create modules so imports resolve. Stub:

- constants for handle, sample size, days back, collection map
- `DERIVED_STAT_KEYS` ordered tuple
- `null_unknowable()` / helpers returning `None` for saved + unfollow fields
- `main.run()` raising `NotImplementedError`

### Phase 2 — Contracts

Lock key names and null rules to the tables above. Stop if anything contradicts plan decisions.

### Phase 3 — Test design (failing)

In `tests/experiments/test_aoc_getrepo_derived_stats_contracts.py`:

1. **Given** constants module **when** imported **then** follower sample is 50, days back is 182, target handle is `aoc.bsky.social`.
2. **Given** `DERIVED_STAT_KEYS` **when** listed **then** exact ordered keys match the contract table.
3. **Given** unknowable fields **when** null helpers applied **then** `saved_posts` and `unfollow_actions` are `None` (not `[]`).
4. **Given** a minimal valid derived-stat dict builder stub **when** built for an empty window **then** list fields that are knowable-empty are `[]` and quote/reply body fields are `None`.

### Phase 4–5

Implement pure constants/schema helpers until contract tests are green. No network. `main.run` may remain `NotImplementedError`.

## Pass / fail

### Must pass before leaving this step

- [ ] Package and contract test file exist at the paths above.
- [ ] `uv run pytest tests/experiments/test_aoc_getrepo_derived_stats_contracts.py -q` green for constants/schema assertions.
- [ ] No edits under `experimentation/aoc_followers_backfill/`.
- [ ] No live API calls in this step’s code paths.

### Must fail / must not happen

- [ ] Implementing discovery or `getRepo` in this step.
- [ ] Setting `saved_posts` or `unfollow_actions` to `[]`.
- [ ] Inferring `account_created_at` from post timestamps in schema helpers.

## Commands

```bash
uv run pytest tests/experiments/test_aoc_getrepo_derived_stats_contracts.py -q
```

Expected: all contract tests pass after schema helpers are filled; import errors mean scaffold incomplete.

## Done when

Constants, key order, null policy, and output layout are locked by tests. Ready for Step 2 discovery against these seams.

# Step 4: Derive stats with mandatory nulls

From decoded `RepoBundle`s plus AppView follower scalars on cohort members, build one derived-stats object per member matching Step 1 keys. Enforce the availability matrix: unknowable fields stay `None`; quote/reply target bodies stay `None`; unfollows and saves stay `None`.

## Scope

- **Caller:** `main.run` will call `derive_stats(cohort_members, repo_bundles, window) -> list[dict]`.
- **Slice:** pure derivation + cohort graph cross-links + pandas-friendly scalar flattening helper.
- **Out of scope:** network I/O; writing files (Step 5).

## Files

### Inspect

- `experiments/aoc_getrepo_derived_stats_2026_08_11/schemas.py` — keys and null helpers
- `experiments/aoc_getrepo_derived_stats_2026_08_11/records.py` / `fetch_repos.py` — bundle shapes from Step 3
- `docs/plans/2026-08-11_aoc_getrepo_derived_stats_dc0868/plan.md` — availability matrix

### Allowed to change

- `experiments/aoc_getrepo_derived_stats_2026_08_11/derive.py` — **create**
- `experiments/aoc_getrepo_derived_stats_2026_08_11/schemas.py` — builders only if needed
- `tests/experiments/test_aoc_getrepo_derived_stats_derive.py` — **create**

### Forbidden to change

- `experimentation/aoc_followers_backfill/**`
- Discovery / fetch modules’ network behavior
- Any hydration client calls

## Behavior requirements

For each member with a successful bundle:

| Field | Rule |
|---|---|
| `handle` | From cohort member; else `None` |
| `display_name` | From profile record `displayName` if present; else `None` |
| `bio` | From profile record `description` if present; else `None` |
| `account_created_at` | Profile `createdAt` if present; else `None` (never min post time) |
| `original_posts` | Posts in window with no `reply` |
| `liked_posts` / `reposted_posts` | Likes / reposts in window |
| `quoted_posts` | Posts in window with quote embed URI; `quoted_post_body=None` always |
| `replied_posts` | Posts in window with `reply`; `parent_post_body=None` always |
| `saved_posts` | Always `None` |
| `cohort_followees` | Still-present follows whose `followed_did` ∈ cohort DIDs |
| `cohort_followers` | Other cohort members whose still-present follows include this `did` |
| `followers_count` | AppView value from cohort member; else `None` |
| `followees_count` | `len(all still-present follows)` (not window-filtered) |
| `follow_actions` | Still-present follows with `createdAt` in window |
| `unfollow_actions` | Always `None` |

For members with fetch/decode `error`: still emit an object with `did`/`handle`, mandatory `None`s for unknowable fields, empty lists only where knowable-empty is honest, and leave activity lists empty; do not fabricate profile fields.

## Implement-from-spec phases

### Phase 0

Pure function `derive_stats(...)` with no I/O.

### Phase 1 — Scaffold

Stub derive module + tests importing it.

### Phase 2 — Contracts

Output keys == `DERIVED_STAT_KEYS` exactly.

### Phase 3 — Test design

1. **Given** synthetic posts (original, reply, quote) **when** derive **then** split into the correct list fields; quote/reply bodies are `None`.
2. **Given** likes/reposts in and out of window **when** derive **then** only in-window entries appear.
3. **Given** follow edges among three cohort DIDs **when** derive **then** `cohort_followers` / `cohort_followees` match still-present edges.
4. **Given** follows created in window and older follows **when** derive **then** `follow_actions` only in-window; `followees_count` counts all still-present.
5. **Given** any bundle **when** derive **then** `saved_posts is None` and `unfollow_actions is None`.
6. **Given** profile without `createdAt` but with old posts **when** derive **then** `account_created_at is None`.
7. **Given** AppView `followers_count=123` on member **when** derive **then** `followers_count == 123`.
8. **Given** errored bundle **when** derive **then** object still has required keys and null policy held.

### Phase 4 — Flesh UoWs

1. Per-member activity lists.
2. Profile scalars + account created null rule.
3. Cohort graph cross-link pass (requires all bundles).
4. Errored-member emission.

### Phase 5

All derive tests green offline.

## Pass / fail

### Must pass

- [ ] `uv run pytest tests/experiments/test_aoc_getrepo_derived_stats_derive.py -q` green.
- [ ] No test constructs non-`None` `saved_posts` or `unfollow_actions` as expected outputs.
- [ ] No `getPosts` usage in `derive.py`.

### Must fail / must not happen

- [ ] Inferring account creation from earliest post.
- [ ] Hydrating quote/parent bodies.
- [ ] Using AppView for anything other than the already-attached `followers_count` on the member object.

## Commands

```bash
uv run pytest tests/experiments/test_aoc_getrepo_derived_stats_derive.py tests/experiments/test_aoc_getrepo_derived_stats_contracts.py -q
```

Expected: all pass without network.

## Done when

Derivation produces complete per-member objects obeying the null matrix and cohort graph rules. Ready for Step 5 orchestration and outputs.

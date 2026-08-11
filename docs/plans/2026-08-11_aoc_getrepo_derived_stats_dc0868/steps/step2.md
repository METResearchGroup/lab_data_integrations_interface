# Step 2: Cohort discovery (AOC DID + 50 most recent follower DIDs)

Implement discovery against the public AppView client so the experiment obtains AOC’s DID and her 50 most recent followers with no qualification filters. Also fetch AppView scalar follower counts for each cohort member (allowed exception to getRepo-only).

## Scope

- **Caller:** `experiments/aoc_getrepo_derived_stats_2026_08_11/main.py` will call discovery then fetch (fetch is Step 3).
- **Slice:** resolve AOC → page newest-first followers until 50 → build cohort list of 51 members including AOC → attach AppView `followers_count` per member.
- **Out of scope:** `getRepo`, CAR decode, derived-stat assembly, writing outputs.

## Files

### Inspect

- `experimentation/aoc_followers_backfill/client.py` — `create_public_client()` (import; do not modify)
- `experimentation/aoc_followers_backfill/discovery.py` — `get_follower_dids(client, n)` newest-first pagination pattern (import or mirror locally; prefer calling/adapting without editing the shared module unless a tiny reusable helper is clearly needed—default: implement experiment-local discovery that follows the same paging pattern)
- `experiments/aoc_getrepo_derived_stats_2026_08_11/constants.py` — sample size 50, target handle
- `tests/experiments/test_aoc_getrepo_derived_stats_contracts.py` — prior contracts

### Allowed to change

- `experiments/aoc_getrepo_derived_stats_2026_08_11/discovery.py` — **create**
- `experiments/aoc_getrepo_derived_stats_2026_08_11/constants.py` — page-size constant only if needed
- `tests/experiments/test_aoc_getrepo_derived_stats_discovery.py` — **create** (mocked AppView)

### Forbidden to change

- `experimentation/aoc_followers_backfill/discovery.py` (unless a one-line export is unavoidable—prefer experiment-local)
- `experimentation/aoc_followers_backfill/client.py`
- Relay / `getRepo` modules
- `data_platform/**`

## Behavior requirements

1. Use `create_public_client()` from `experimentation.aoc_followers_backfill.client`.
2. Resolve target profile for `aoc.bsky.social`; record `did`, `handle`, `display_name` if present on the profile view, and `followers_count`.
3. Page `app.bsky.graph.getFollowers` with limit 100 (or existing page size), newest-first, until 50 followers collected or list exhausted.
4. Build cohort as `[AOC] + followers` (AOC first). Length must be `1 + min(50, available)`.
5. For each follower not already fully profiled, batch-fetch profiles as needed so every cohort member has AppView `followers_count` (or `None` if that member’s profile call failed).
6. Do **not** apply min-follower or recent-post filters from the old backfill.
7. Return a structure tests can assert: list of member dicts with at least `did`, `handle`, `followers_count`, and `is_seed` (True only for AOC).

## Implement-from-spec phases

### Phase 0

Caller path piece: `discover_cohort(client) -> CohortResult`.

### Phase 1 — Scaffold

Create `discovery.py` with stub `discover_cohort` raising `NotImplementedError`; tests import it.

### Phase 2 — Contracts

Public function signatures frozen; member dict keys frozen in tests.

### Phase 3 — Test design (mocked)

1. **Given** mocked profile + one followers page of 50 **when** discover **then** cohort length 51, first member is AOC, `is_seed` True only on first.
2. **Given** mocked followers page of only 3 **when** discover **then** cohort length 4 (no padding).
3. **Given** two pages needed (e.g. 100 then 20) **when** requesting 50 **then** stops at 50 followers + AOC = 51; does not consume endlessly.
4. **Given** profile batch missing `followers_count` **when** discover **then** that member’s `followers_count` is `None`.
5. **Given** discovery **when** run **then** no relay client is constructed.

### Phase 4 — Flesh UoWs

1. Resolve AOC profile.
2. Page followers to 50.
3. Attach follower counts for all members.
4. Assemble ordered cohort.

### Phase 5

Discovery unit tests green without network.

## Pass / fail

### Must pass

- [ ] `uv run pytest tests/experiments/test_aoc_getrepo_derived_stats_discovery.py -q` green.
- [ ] Contract tests from Step 1 still green.
- [ ] Discovery uses public AppView client only.

### Must fail / must not happen

- [ ] Reintroducing `MIN_FOLLOWERS` / `MIN_POSTS_LAST_7_DAYS` filters.
- [ ] Calling `getRepo` or `create_relay_client` from discovery.
- [ ] Mutating shared backfill discovery behavior used by other scripts (prefer experiment-local).

## Commands

```bash
uv run pytest tests/experiments/test_aoc_getrepo_derived_stats_discovery.py tests/experiments/test_aoc_getrepo_derived_stats_contracts.py -q
```

Expected: all pass; no network.

## Done when

`discover_cohort` returns AOC + up to 50 newest followers with AppView follower scalars attached, covered by mocks. Ready for Step 3 repo fetch.

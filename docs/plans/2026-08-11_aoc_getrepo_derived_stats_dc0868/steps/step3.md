# Step 3: getRepo fetch + decode for all 51 DIDs

For each cohort member, call relay `getRepo`, decode via imported MST helpers, and retain posts, likes, reposts, follows, and the profile record. Apply the 182-day window only when selecting activity rows for raw dumps / later derivation inputs—not by discarding the profile record.

## Scope

- **Caller:** `main.run` will call `fetch_cohort_repos(cohort, relay_client)` after discovery.
- **Slice:** per-DID `getRepo` → `decode_repo` → bucket records by collection → attach profile record → surface per-DID errors without aborting the whole cohort.
- **Out of scope:** derived-stat field assembly (Step 4); output writing (Step 5); AppView calls (already done in Step 2).

## Files

### Inspect

- `experimentation/aoc_followers_backfill/mst.py` — `decode_repo` (**import only**)
- `experimentation/aoc_followers_backfill/client.py` — `create_relay_client` (**import only**)
- `experimentation/aoc_followers_backfill/backfill.py` — row builders and quote/reply URI extraction (reuse patterns; prefer importing private helpers only if already public—otherwise reimplement thin row builders in the experiment package without copying MST)
- `strategy_planning/2026-07-15_getrepo_return_type.md` — required/optional fields
- `experiments/aoc_getrepo_derived_stats_2026_08_11/constants.py` — collection map, `DAYS_BACK`

### Allowed to change

- `experiments/aoc_getrepo_derived_stats_2026_08_11/fetch_repos.py` — **create**
- `experiments/aoc_getrepo_derived_stats_2026_08_11/records.py` — **create** (row builders / record classification; no MST fork)
- `experiments/aoc_getrepo_derived_stats_2026_08_11/constants.py` — collection constants if needed
- `tests/experiments/test_aoc_getrepo_derived_stats_fetch.py` — **create** (mocked relay + fixture CAR or synthetic decode output)

### Forbidden to change

- `experimentation/aoc_followers_backfill/mst.py`
- `experimentation/aoc_followers_backfill/client.py`
- `experimentation/aoc_followers_backfill/backfill.py` (do not expand DAYS_BACK defaults there for this experiment)
- Adding a vendored copy of MST walk code under `experiments/`

## Behavior requirements

1. Import `decode_repo` from `experimentation.aoc_followers_backfill.mst` and `create_relay_client` from `experimentation.aoc_followers_backfill.client`.
2. For each cohort member, `com.atproto.sync.get_repo({"did": did})` on the relay client.
3. Decode to `did → records` map; classify by `$type`:
   - `app.bsky.feed.post`
   - `app.bsky.feed.like`
   - `app.bsky.feed.repost`
   - `app.bsky.graph.follow`
   - `app.bsky.actor.profile` (rkey `self` / profile record)
4. Keep **all** records of those types available to Step 4; when emitting window-filtered activity lists, use `createdAt >= window_start` with `window_start = run_start - 182 days`.
5. Profile record is never dropped for being “outside the window.”
6. On `getRepo` or decode failure: store empty collections, `profile=None`, and an error string for that DID; continue to next member.
7. Do not call `getPosts` or any AppView hydration for embed/parent subjects.

## Implement-from-spec phases

### Phase 0

UoW: `fetch_one_repo(member, relay_client, window) -> RepoBundle` then `fetch_cohort_repos(...)`.

### Phase 1 — Scaffold

Stubs for `fetch_one_repo` / `fetch_cohort_repos` / row classifiers.

### Phase 2 — Contracts

`RepoBundle` fields: `did`, `handle`, `posts`, `likes`, `reposts`, `follows`, `profile`, `error`.

### Phase 3 — Test design

1. **Given** mocked `get_repo` returning bytes and mocked `decode_repo` returning mixed collections **when** fetch one **then** bundles split correctly and profile retained.
2. **Given** posts older and newer than window **when** window filter helper applied **then** only in-window activity retained for activity lists; profile still present.
3. **Given** `get_repo` raises **when** fetch one **then** error set, collections empty, cohort loop continues.
4. **Given** quote embed and reply shapes **when** classifiers run **then** `quoted_post_uri` / reply parent-root URIs extracted; no network hydration.
5. **Given** fetch module source **when** inspected by test or review **then** imports `decode_repo` from `experimentation.aoc_followers_backfill.mst` (no local MST walk).

### Phase 4 — Flesh UoWs

1. Relay fetch + decode import wiring.
2. Classification + quote/reply URI extraction.
3. Window filter helper.
4. Per-DID error isolation for cohort fetch.

### Phase 5

Fetch unit tests green with mocks; no live relay required.

## Pass / fail

### Must pass

- [ ] `uv run pytest tests/experiments/test_aoc_getrepo_derived_stats_fetch.py -q` green.
- [ ] MST is imported from `experimentation.aoc_followers_backfill.mst`, not copied.
- [ ] Failed DIDs do not raise out of `fetch_cohort_repos`.

### Must fail / must not happen

- [ ] Copying `mst.py` into the experiment package.
- [ ] Hydrating subject posts via AppView/`getPosts`.
- [ ] Dropping profile because it lacks an in-window `createdAt`.

## Commands

```bash
uv run pytest tests/experiments/test_aoc_getrepo_derived_stats_fetch.py tests/experiments/test_aoc_getrepo_derived_stats_contracts.py -q
```

Expected: all pass without network.

## Done when

Each cohort DID yields a `RepoBundle` (or explicit error) with decoded collections and profile, using imported MST decode. Ready for Step 4 derivation.

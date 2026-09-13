# Step 3: getRepo fetch, decode, and resume cache

For each member, call relay `getRepo` and decode with the existing helpers, or load a decoded bundle from the per-DID cache. Keep posts, likes, reposts, follows, and the profile record. Record per-DID failures and continue. Do not apply the 365-day window here. Windowing is Step 4. Do not call `getPosts`.

## Scope

- **Caller:** `main.run` will call profile fetch, then repo fetch with cache.
- **Slice:** per-DID cache lookup → `getRepo` on miss → `decode_repo` → write cache → attach `account_created_at` from the repo profile record.
- **Out of scope:** activity CSVs, `getPosts`, follow graph files, writing the timestamped CSV folder.

## Files

### Inspect

- `experimentation/aoc_followers_backfill/mst.py` (`decode_repo`, import only)
- `experimentation/aoc_followers_backfill/client.py` (`create_relay_client`, import only)
- `experiments/aoc_getrepo_derived_stats_2026_08_11/fetch_repos.py` (`fetch_one_repo`, `RepoBundle`, `classify_records`)
- `experiments/aoc_getrepo_derived_stats_2026_08_11/records.py` (`PostRow`, `LikeOrRepostRow`, `FollowRow`, `ProfileRecord`)
- `experiments/aoc_getrepo_derived_stats_2026_08_11/discovery.py` (`CohortMember`, only as the type `fetch_one_repo` expects)

### Allowed to change

- `experiments/data_request_2026_08_14/fetch_repos.py` (create)
- `experiments/data_request_2026_08_14/constants.py` (cache root path)
- `experiments/data_request_2026_08_14/profiles.py` (add a helper that copies `ProfileRecord.created_at` onto `account_created_at`, and nothing else)
- `tests/experiments/test_data_request_2026_08_14_fetch.py` (create, mocked relay and mocked decode)

### Forbidden to change

- `experimentation/aoc_followers_backfill/mst.py`
- `experimentation/aoc_followers_backfill/client.py`
- `experiments/aoc_getrepo_derived_stats_2026_08_11/**` (import only)
- Adding a local copy of MST walk code under `experiments/data_request_2026_08_14/`

## Behavior requirements

1. Import `decode_repo` from `experimentation.aoc_followers_backfill.mst` by going through `experiments.aoc_getrepo_derived_stats_2026_08_11.fetch_repos.fetch_one_repo`. Do not copy MST parsing.
2. Cache directory is `experiments/data_request_2026_08_14/cache/repos/`. One successful DID writes one JSON file named by replacing `:` in the DID with `_` (e.g. `did_plc_abc.json`). A failed DID writes `did_plc_abc.error.json` with the error string. Do not treat an error file as a success cache hit.
3. If the success JSON exists and loads, do not call `getRepo` for that DID. Rebuild `RepoBundle` from the file.
4. Build the `CohortMember` that `fetch_one_repo` expects (`did`, `handle`, `followers_count=None`, `display_name=None`, `is_seed=False`). Handle may be the AppView handle from Step 2, or an empty string if the profile call failed.
5. On a cache miss, call `fetch_one_repo`. Isolate failures. A failed DID returns empty collections and an error string, then writes the error file.
6. Keep every post, like, repost, and follow record on the bundle. Do not drop records for being older than 365 days.
7. Keep the profile record even when it has no `createdAt`.
8. After a successful bundle, if `bundle.profile.created_at` is present, set the matching profile row `account_created_at` to that value. If `created_at` is missing, leave `account_created_at` as `None`. Never use the earliest post time.
9. Map bundle errors into fetch-error dicts with `stage="getRepo"` or `stage="decode"` from the error string prefix already used in `fetch_one_repo` (`getRepo failed:` vs `CAR/MST decode failed:` vs `record classification failed:`).
10. Do not call `getPosts` here. Do not retry error-file DIDs unless a `retry_errors=True` argument is set (default false). Tests must cover skip-on-hit and skip-on-error-file.

## Implement-from-spec phases

### Phase 0. Scope

Unit of work: `fetch_member_repos(members, profile_rows, relay_client, cache_dir, retry_errors=False) -> RepoFetchResult`.

`RepoFetchResult` holds a list of `RepoBundle` (one per member, input order) and extra fetch-error dicts for the writer in Step 5.

### Phase 1. Scaffold

Stubs for `fetch_member_repos`, cache read/write, and attaching profile-record `createdAt`.

### Phase 2. Contracts

One bundle per member. Profile-row `account_created_at` is either the repo profile `createdAt` or `None`. Cache path convention is locked by tests.

### Phase 3. Test design

1. **Given** a mocked `fetch_one_repo` returning posts, likes, a follow, and a profile with `createdAt` **when** fetch **then** the bundle keeps those collections, the profile row `account_created_at` matches the profile record, and a success JSON appears under `cache_dir`.
2. **Given** a success JSON already in `cache_dir` **when** fetch **then** `fetch_one_repo` is not called for that DID, and the bundle matches the cached collections.
3. **Given** an error JSON in `cache_dir` and `retry_errors=False` **when** fetch **then** `fetch_one_repo` is not called, collections are empty, and an error dict is emitted.
4. **Given** a profile record with no `createdAt` and old posts **when** attach createdAt **then** `account_created_at` stays `None`.
5. **Given** `fetch_one_repo` returning `error="getRepo failed: ..."` **when** fetch **then** collections are empty, the loop continues, an error dict has `stage="getRepo"`, and an error JSON is written.
6. **Given** `fetch_repos.py` source **when** read **then** it imports `fetch_one_repo` from `experiments.aoc_getrepo_derived_stats_2026_08_11.fetch_repos` and does not define a local MST walker.

### Phase 4. Flesh units of work

1. Cache path helpers and skip-on-hit.
2. Adapt each member into `CohortMember` and call `fetch_one_repo` on miss.
3. Attach profile-record `createdAt`.
4. Collect per-DID errors without aborting.

### Phase 5. Done

Fetch unit tests green without network.

## Pass / fail

### Must pass

- [ ] `uv run pytest tests/experiments/test_data_request_2026_08_14_fetch.py -q` is green.
- [ ] Step 1 and Step 2 tests stay green.
- [ ] Decode goes through the existing `fetch_one_repo` import.
- [ ] A second fetch of the same DID does not call `getRepo` when the success cache file exists.

### Must fail / must not happen

- [ ] Copying MST walk code into this experiment.
- [ ] Filtering records by the 365-day window before Step 4.
- [ ] Setting `account_created_at` from the earliest post.
- [ ] Calling `getPosts` before Step 6.
- [ ] Restarting finished DIDs after a crash when their success JSON exists.

## Commands

```bash
uv run pytest tests/experiments/test_data_request_2026_08_14_fetch.py tests/experiments/test_data_request_2026_08_14_profiles.py tests/experiments/test_data_request_2026_08_14_contracts.py -q
```

Expected: all pass, no network.

## Done when

Every member has a `RepoBundle` (from cache or a live fetch, possibly errored), success and error files land under the cache dir, and profile rows have `account_created_at` only from the repo profile record. Ready for Step 4 activity tables with no AppView lookup.

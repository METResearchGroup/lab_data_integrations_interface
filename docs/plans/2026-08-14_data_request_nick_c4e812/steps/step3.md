# Step 3: getRepo fetch and decode

For each member, call relay `getRepo` and decode with the existing helpers. Keep posts, likes, reposts, follows, and the profile record. Record per-DID failures and continue. Do not apply the 365-day window here. Windowing is Step 4.

## Scope

- **Caller:** `main.run` will call profile fetch, then repo fetch.
- **Slice:** per-DID `getRepo` → `decode_repo` → classified collections on a bundle → optional fill of `account_created_at` on the profile row from the repo profile record.
- **Out of scope:** activity CSVs, `getPosts`, follow graph files, writing the timestamped folder.

## Files

### Inspect

- `experimentation/aoc_followers_backfill/mst.py` (`decode_repo`, import only)
- `experimentation/aoc_followers_backfill/client.py` (`create_relay_client`, import only)
- `experiments/aoc_getrepo_derived_stats_2026_08_11/fetch_repos.py` (`fetch_one_repo`, `RepoBundle`, `classify_records`)
- `experiments/aoc_getrepo_derived_stats_2026_08_11/records.py` (`PostRow`, `LikeOrRepostRow`, `FollowRow`, `ProfileRecord`)
- `experiments/aoc_getrepo_derived_stats_2026_08_11/discovery.py` (`CohortMember`, only as the type `fetch_one_repo` expects)

### Allowed to change

- `experiments/data_request_2026_08_14/fetch_repos.py` (create)
- `experiments/data_request_2026_08_14/profiles.py` (add a helper that copies `ProfileRecord.created_at` onto `account_created_at`, and nothing else)
- `tests/experiments/test_data_request_2026_08_14_fetch.py` (create, mocked relay and mocked decode)

### Forbidden to change

- `experimentation/aoc_followers_backfill/mst.py`
- `experimentation/aoc_followers_backfill/client.py`
- `experiments/aoc_getrepo_derived_stats_2026_08_11/**` (import only)
- Adding a local copy of MST walk code under `experiments/data_request_2026_08_14/`

## Behavior requirements

1. Import `decode_repo` from `experimentation.aoc_followers_backfill.mst` by going through `experiments.aoc_getrepo_derived_stats_2026_08_11.fetch_repos.fetch_one_repo`. Do not copy MST parsing.
2. Build the `CohortMember` that `fetch_one_repo` expects (`did`, `handle`, `followers_count=None`, `display_name=None`, `is_seed=False`). Handle may be the AppView handle from Step 2, or an empty string if the profile call failed.
3. Call `fetch_one_repo` once per member. Isolate failures. A failed DID returns empty collections and an error string.
4. Keep every post, like, repost, and follow record on the bundle. Do not drop records for being older than 365 days.
5. Keep the profile record even when it has no `createdAt`.
6. After a successful bundle, if `bundle.profile.created_at` is present, set the matching profile row `account_created_at` to that value. If `created_at` is missing, leave `account_created_at` as `None`. Never use the earliest post time.
7. Map bundle errors into fetch-error dicts with `stage="getRepo"` or `stage="decode"` from the error string prefix already used in `fetch_one_repo` (`getRepo failed:` vs `CAR/MST decode failed:` vs `record classification failed:`).
8. Do not call `getPosts` here.

## Implement-from-spec phases

### Phase 0. Scope

Unit of work: `fetch_member_repos(members, profile_rows, relay_client) -> RepoFetchResult`.

`RepoFetchResult` holds a list of `RepoBundle` (one per member, input order) and extra fetch-error dicts for the writer in Step 5.

### Phase 1. Scaffold

Stubs for `fetch_member_repos` and for attaching profile-record `createdAt`.

### Phase 2. Contracts

One bundle per member. Profile-row `account_created_at` is either the repo profile `createdAt` or `None`.

### Phase 3. Test design

1. **Given** a mocked `fetch_one_repo` returning posts, likes, a follow, and a profile with `createdAt` **when** fetch **then** the bundle keeps those collections and the profile row `account_created_at` matches the profile record.
2. **Given** a profile record with no `createdAt` and old posts **when** attach createdAt **then** `account_created_at` stays `None`.
3. **Given** `fetch_one_repo` returning `error="getRepo failed: ..."` **when** fetch **then** collections are empty, the loop continues, and an error dict has `stage="getRepo"`.
4. **Given** `fetch_repos.py` source **when** read **then** it imports `fetch_one_repo` from `experiments.aoc_getrepo_derived_stats_2026_08_11.fetch_repos` and does not define a local MST walker.

### Phase 4. Flesh units of work

1. Adapt each member into `CohortMember` and call `fetch_one_repo`.
2. Attach profile-record `createdAt`.
3. Collect per-DID errors without aborting.

### Phase 5. Done

Fetch unit tests green without network.

## Pass / fail

### Must pass

- [ ] `uv run pytest tests/experiments/test_data_request_2026_08_14_fetch.py -q` is green.
- [ ] Step 1 and Step 2 tests stay green.
- [ ] Decode goes through the existing `fetch_one_repo` import.

### Must fail / must not happen

- [ ] Copying MST walk code into this experiment.
- [ ] Filtering records by the 365-day window before Step 4.
- [ ] Setting `account_created_at` from the earliest post.
- [ ] Calling `getPosts` before Step 4.

## Commands

```bash
uv run pytest tests/experiments/test_data_request_2026_08_14_fetch.py tests/experiments/test_data_request_2026_08_14_profiles.py tests/experiments/test_data_request_2026_08_14_contracts.py -q
```

Expected: all pass, no network.

## Done when

Every member has a `RepoBundle` (possibly errored), and profile rows have `account_created_at` only from the repo profile record. Ready for Step 4 windowed activity and post lookups.

# Step 2: Profile fields for every DID

Load current handle, display name, bio, and platform follower and followee counts from public AppView profile calls. Write in-memory profile rows that match `profiles.csv`. Leave `account_created_at` empty until Step 3 copies it from the getRepo profile record.

## Scope

- **Caller:** `main.run` will call member load, then profile fetch, then repo fetch (repo fetch is Step 3).
- **Slice:** batch AppView `getProfiles` for every DID in the member list. Attach `window_start` and `window_end`. Record per-DID profile failures without stopping the cohort.
- **Out of scope:** `getRepo`, CAR decode, activity tables, `getPosts`, writing output files.

## Files

### Inspect

- `experimentation/aoc_followers_backfill/client.py` (`create_public_client`, import only)
- `experiments/aoc_getrepo_derived_stats_2026_08_11/discovery.py` (`_profiles_by_did` and `PROFILES_BATCH_SIZE = 25`, copy the batching idea locally)
- `experiments/data_request_2026_08_14/schemas.py` (`PROFILES_CSV_FIELDNAMES`)
- `experiments/data_request_2026_08_14/members.py`

### Allowed to change

- `experiments/data_request_2026_08_14/profiles.py` (create)
- `experiments/data_request_2026_08_14/constants.py` (add `PROFILES_BATCH_SIZE = 25` if needed)
- `tests/experiments/test_data_request_2026_08_14_profiles.py` (create, mocked AppView)

### Forbidden to change

- `experimentation/aoc_followers_backfill/client.py`
- `experiments/aoc_getrepo_derived_stats_2026_08_11/discovery.py`
- Relay / `getRepo` modules
- `data_platform/**`

## Behavior requirements

1. Use `create_public_client()` from `experimentation.aoc_followers_backfill.client`.
2. Call `client.app.bsky.actor.get_profiles({"actors": batch})` in batches of 25 DIDs.
3. Map each AppView profile to a row with:
   - `did` from the member list
   - `handle` from AppView
   - `display_name` from AppView `displayName`
   - `bio` from AppView `description`
   - `account_created_at` always `None` until Step 3
   - `window_start` / `window_end` from the run window
   - `followers_count` from AppView `followersCount`
   - `followees_count` from AppView `followsCount` (platform total, not the count of follows inside the member list)
   - `n_pools` and `seeds` copied from the member list
4. If a DID is missing from the AppView response, still emit a profile row with that `did`, copied `n_pools`/`seeds`, window bounds, and nulls for AppView fields. Append a fetch-error dict with `stage="profile"`.
5. Do not call `getRepo` or `create_relay_client` from the profile module.
6. Do not set `account_created_at` from AppView `indexedAt` or from any post timestamp.

## Implement-from-spec phases

### Phase 0. Scope

Caller path piece: `fetch_profiles(client, members, window_start, window_end) -> ProfileFetchResult`.

`ProfileFetchResult` holds `rows` (one per member, member-list order) and `errors` (profile failures only).

### Phase 1. Scaffold

Create `profiles.py` with stub `fetch_profiles` raising `NotImplementedError`. Tests import it.

### Phase 2. Contracts

Public function signature and row keys frozen in tests. Row keys equal `PROFILES_CSV_FIELDNAMES`.

### Phase 3. Test design (mocked)

1. **Given** two members and a mocked `get_profiles` that returns both **when** fetch **then** two rows in input order, with handle, bio, and both counts filled, and `account_created_at` is `None`.
2. **Given** two members and a mocked response that omits the second DID **when** fetch **then** the second row still exists with null AppView fields, and `errors` has one item with `stage="profile"`.
3. **Given** 26 DIDs **when** fetch **then** `get_profiles` is called twice (25 then 1).
4. **Given** `followsCount=10` on AppView **when** fetch **then** `followees_count == 10` (do not count repo follow records).
5. **Given** the profiles module **when** imported **then** it does not import `create_relay_client` or `decode_repo`.

### Phase 4. Flesh units of work

1. Batch `get_profiles`.
2. Map AppView fields onto contract columns.
3. Emit a row plus an error when a DID is missing.

### Phase 5. Done

Profile unit tests green without network.

## Pass / fail

### Must pass

- [ ] `uv run pytest tests/experiments/test_data_request_2026_08_14_profiles.py -q` is green.
- [ ] Contract tests from Step 1 stay green.
- [ ] Profile fetch uses the public AppView client only.

### Must fail / must not happen

- [ ] Setting `account_created_at` from posts or from AppView `indexedAt`.
- [ ] Calling `getRepo` from `profiles.py`.
- [ ] Dropping a member who has no AppView profile (the row must still exist).

## Commands

```bash
uv run pytest tests/experiments/test_data_request_2026_08_14_profiles.py tests/experiments/test_data_request_2026_08_14_contracts.py -q
```

Expected: all pass, no network.

## Done when

`fetch_profiles` returns one contract row per member, with AppView scalars attached when present, covered by mocks. Ready for Step 3 repo fetch.

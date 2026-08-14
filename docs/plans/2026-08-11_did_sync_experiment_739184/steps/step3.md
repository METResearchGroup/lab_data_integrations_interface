# Step 3: Implement Ablation 2, AOC follower breadth first search

## Goal

Collect 1000 unique DIDs by starting at AOC and walking followers in breadth first order. Stop as soon as 1000 unique DIDs are in hand.

## Scope

The main caller is `discover_aoc_bfs_dids(target: int, client: Client | None = None) -> DiscoveryResult`, called from `run_experiment.py`.

The work in this step is resolving AOC, paging `getFollowers`, maintaining a queue and a seen set, stopping at `target` unique DIDs, and recording discovery metrics.

PLC discovery changes, `getRepo` enrichment, and writing `RESULTS.md` are out of scope.

## Files to inspect

- [`experimentation/aoc_followers_backfill/discovery.py`](../../../experimentation/aoc_followers_backfill/discovery.py) for `get_followers` paging patterns
- [`experimentation/aoc_followers_backfill/client.py`](../../../experimentation/aoc_followers_backfill/client.py) for `create_public_client`
- [`experimentation/aoc_followers_backfill/constants.py`](../../../experimentation/aoc_followers_backfill/constants.py) for `TARGET_HANDLE` and `FOLLOWERS_PAGE_SIZE`
- [`experiments/did_sync_experiment_2026_08_11/discover.py`](../../../experiments/did_sync_experiment_2026_08_11/discover.py) from Steps 1 and 2

## Files allowed to change

- `experiments/did_sync_experiment_2026_08_11/discover.py`
- `experiments/did_sync_experiment_2026_08_11/constants.py` only if AOC handle wiring needs a small fix
- `tests/experiments/did_sync_experiment_2026_08_11/test_discover.py`

## Files forbidden to change

- `experimentation/aoc_followers_backfill/**` (import only)
- `data_platform/**`
- `analyze.py` business logic, which stays stubbed until Step 4

## Algorithm

1. Build or accept a public AppView client via `create_public_client()`.
2. Resolve `aoc.bsky.social` with `get_profile`, and read the seed DID and follower count into `extra`.
3. Initialize a queue with the seed DID for expansion, and an empty ordered list for collected follower DIDs. Do not count AOC herself toward the 1000 unless she appears as someone else's follower, which she should not.
4. While the collected unique DID list length is below `target` and the queue is not empty, pop the next DID to expand.
5. Page `app.bsky.graph.get_followers` with `FOLLOWERS_PAGE_SIZE` until that account's follower list is exhausted or `target` is reached. For each follower DID not yet seen, append it to the result list and enqueue it for later expansion. Count every successful follower page call in `request_count`.
6. Stop immediately when `len(dids) == target`. Do not keep paging the current account after the target is met.
7. On rate limit errors, record a rate limit event, sleep briefly, and retry the same page.

Store at least these fields in `extra`:

- `seed_handle`
- `seed_did`
- `seed_followers_count` when available
- `max_depth_reached`
- `pages_by_depth` as a map of depth to page count

Depth 0 means pages taken while expanding AOC. Depth 1 means pages taken while expanding AOC's followers, and so on.

## Unit tests required

Mock the AppView client. Do not call Bluesky live.

1. Breadth first ordering collects followers of the seed before followers of those followers when `target` is large enough to need depth 2.
2. Collection stops at exactly `target` unique DIDs even when more followers remain on the current page.
3. Duplicate follower DIDs across pages are ignored.
4. Rate limit on a follower page increments `rate_limit_events`, and the run still completes after a mocked retry.
5. `extra["seed_handle"]` equals `aoc.bsky.social`.

## Pass

- `PYTHONPATH=. uv run pytest tests/experiments/did_sync_experiment_2026_08_11/test_discover.py -k aoc -q` exits 0.
- A mocked graph with more than 50 followers returns exactly 50 DIDs when `target=50`.
- AOC's own DID is not included in the collected list.

## Fail

- Continuing past 1000 unique DIDs.
- Reimplementing follower paging inside `data_platform/`.
- Live network calls in unit tests.

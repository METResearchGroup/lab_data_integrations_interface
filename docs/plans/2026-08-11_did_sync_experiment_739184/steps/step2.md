# Step 2: Implement Ablation 1, PLC directory discovery from a recent cursor

## Goal

Collect 1000 unique DIDs from the Bluesky PLC directory export, starting near the recent end of the operation log. Record how many requests ran, how long the walk took, and whether rate limits hit.

## Scope

The main caller is `discover_plc_dids(target: int) -> DiscoveryResult`, called from `run_experiment.py`.

The work in this step is recent cursor selection, paginated PLC export, unique DID collection, rate limit recording, and helpers that serialize `discovery.json`.

AOC follower search, `getRepo`, validity scoring, and the live full experiment run are out of scope.

## Files to inspect

- [`experiments/did_sync_experiment_2026_08_11/constants.py`](../../../experiments/did_sync_experiment_2026_08_11/constants.py) from Step 1
- PLC export behavior documented at `https://web.plc.directory/spec/v0.1/did-plc` (count max 1000, `after` cursor)
- Prior draft behavior on branch `origin/cursor/did-sync-experiment-7833` under `discover.py` for reference only. Do not start from the beginning of the log.

## Files allowed to change

- `experiments/did_sync_experiment_2026_08_11/discover.py`
- `experiments/did_sync_experiment_2026_08_11/constants.py` only if a PLC lookback constant needs a small fix
- `tests/experiments/did_sync_experiment_2026_08_11/test_discover.py`

## Files forbidden to change

- `experimentation/aoc_followers_backfill/**`
- `data_platform/**`
- `analyze.py` and `run_experiment.py`, except imports needed for typing, unless a tiny shared dataclass moves

## Recent cursor rule

Do not start with an empty `after` cursor, because an empty cursor walks from the beginning of the PLC log.

Compute the first `after` value as an ISO 8601 UTC timestamp equal to run start minus `PLC_RECENT_LOOKBACK_HOURS` (24 hours). Page forward with `count=1000`. Collect unique `did` values until `target` is reached.

If the first lookback window yields fewer than `target` unique DIDs after the available pages in that window end, double the lookback from 24 hours to 48 hours, then to 96 hours, and so on. Resume from the earlier cursor, still skipping DIDs already seen, until `target` is reached or a hard stop of 30 days lookback is hit. If 30 days still cannot fill `target`, return what was collected and record the shortfall in `extra`.

Store at least these fields in `extra`:

- `initial_after`
- `final_after`
- `pages`
- `lookback_hours_final`
- `rate_limit_header_sample` when present

On HTTP 429, append a rate limit event. Sleep using `Retry-After` when that header is numeric. Otherwise sleep 5 seconds. Then retry the same page.

## Unit tests required

Use mocked HTTP responses, not live PLC.

1. Unique DID collection skips repeated DID rows across create and update operations.
2. The first request includes a non empty `after` query parameter derived from the lookback rule.
3. Paging stops once `target` unique DIDs are collected.
4. A mocked 429 produces one rate limit event, and a successful retry still returns DIDs.
5. `DiscoveryResult.to_dict()` includes the frozen keys from Step 1.

## Pass

- `PYTHONPATH=. uv run pytest tests/experiments/did_sync_experiment_2026_08_11/test_discover.py -k plc -q` exits 0.
- Calling `discover_plc_dids(target=3)` against mocks returns three unique DIDs, `request_count >= 1`, and `runtime_seconds > 0`.
- No test starts PLC export without an `after` cursor.

## Fail

- Starting from the beginning of the PLC log, or omitting `after` on the first request.
- Returning duplicate DIDs in `dids`.
- Live network calls inside unit tests.

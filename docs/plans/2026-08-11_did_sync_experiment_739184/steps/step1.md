# Step 1: Scaffold the experiment package and freeze outputs

## Goal

Create the experiment package shell so later steps can fill in discovery, enrichment, and results without renaming paths or schemas.

## Scope

The main caller is `experiments/did_sync_experiment_2026_08_11/run_experiment.py`. Operators invoke it with `uv run python -m experiments.did_sync_experiment_2026_08_11.run_experiment`.

The work in this step is the package layout, constants, empty modules with contracts, command line argument parsing that prints help, and failing unit tests that check the frozen schemas.

Live PLC or Bluesky calls are out of scope. Real discovery, real `getRepo` enrichment, and writing `RESULTS.md` from live data are also out of scope.

## Files to inspect

- [`experimentation/aoc_followers_backfill/client.py`](../../../experimentation/aoc_followers_backfill/client.py)
- [`experimentation/aoc_followers_backfill/mst.py`](../../../experimentation/aoc_followers_backfill/mst.py)
- [`experimentation/aoc_followers_backfill/constants.py`](../../../experimentation/aoc_followers_backfill/constants.py)
- [`experiments/x_fetch_data_2026_06_01/main.py`](../../../experiments/x_fetch_data_2026_06_01/main.py)
- [`docs/design_docs/2026-07-17_bluesky_backfill_app.md`](../../../docs/design_docs/2026-07-17_bluesky_backfill_app.md)

## Files allowed to change

- `experiments/did_sync_experiment_2026_08_11/__init__.py`
- `experiments/did_sync_experiment_2026_08_11/constants.py`
- `experiments/did_sync_experiment_2026_08_11/discover.py`
- `experiments/did_sync_experiment_2026_08_11/analyze.py`
- `experiments/did_sync_experiment_2026_08_11/run_experiment.py`
- `experiments/did_sync_experiment_2026_08_11/README.md`
- `tests/experiments/did_sync_experiment_2026_08_11/__init__.py`
- `tests/experiments/did_sync_experiment_2026_08_11/test_constants_and_cli.py`
- `tests/experiments/did_sync_experiment_2026_08_11/test_discover.py`
- `tests/experiments/did_sync_experiment_2026_08_11/test_analyze.py`
- `tests/experiments/did_sync_experiment_2026_08_11/test_run_experiment.py`

## Files forbidden to change

- Everything under `data_platform/`
- Everything under `experimentation/aoc_followers_backfill/` (import only)
- Unrelated experiment packages

## Contracts to freeze

### Constants in `constants.py`

| Name | Value | Meaning |
|---|---|---|
| `TARGET_DIDS` | `1000` | Default unique DID count per ablation |
| `SMOKE_TARGET_DIDS` | `50` | Default smoke size documented in README |
| `DAYS_BACK` | `183` | Six month activity window |
| `MIN_FOLLOWERS` | `10` | Validity rule 1 |
| `MIN_FOLLOWEES` | `10` | Validity rule 2 |
| `MIN_ORIGINAL_POSTS_6M` | `20` | Validity rule 3 |
| `MIN_INTERACTIONS_6M` | `20` | Validity rule 4 |
| `PLC_EXPORT_URL` | `https://plc.directory/export` | Ablation 1 endpoint |
| `PLC_PAGE_SIZE` | `1000` | Max PLC export page size |
| `PLC_RECENT_LOOKBACK_HOURS` | `24` | Initial recent cursor lookback before run start |
| `AOC_HANDLE` | import or mirror `aoc.bsky.social` from AOC backfill constants | Ablation 2 seed |
| `FOLLOWERS_PAGE_SIZE` | reuse `100` from AOC backfill constants | AppView follower page size |
| `PROFILES_BATCH_SIZE` | reuse `25` from AOC backfill constants | AppView profile batch size |
| `ABLATION1_NAME` | `ablation1_plc` | Output directory name |
| `ABLATION2_NAME` | `ablation2_aoc_bfs` | Output directory name |

### Discovery result shape

Each discovery function returns an object that serializes to JSON with at least these fields:

- `ablation` (string)
- `did_count` (int)
- `dids` (list of strings)
- `request_count` (int)
- `runtime_seconds` (float)
- `rate_limit_events` (list of objects with `source`, `at_unix`, `status_code`, `detail`, and optional `retry_after`)
- `extra` (object for ablation specific fields)

### Profile row shape

Each enriched DID serializes with at least these fields:

- `did`, `handle`, `followers`, `followees`, `posts`, `account_created_at`
- six month counts for `original_posts_6m` and `interactions_6m`
- interaction parts for `likes_6m`, `reposts_6m`, `replies_6m`, `quotes_6m`, and `bookmarks_6m`
- `valid` (bool, or null on hard failure)
- `invalid_reasons` (list of strings)
- `error` (string or null)

### Summary shape

Each ablation writes `summary.json` with these fields:

- `ablation`
- `did_count`
- `valid_did_count`
- `invalid_did_count`
- `validity_rate`
- nested `discovery` and `analysis` metric objects

### Command line interface

`run_experiment.py` must accept these flags:

- `--target` (int, default `1000`)
- `--workers` (int, default a small parallel pool such as `8`)
- `--only` with choices `both`, `plc`, and `aoc` (default `both`)
- `--smoke` flag that sets target to `50` when `--target` is omitted

Bodies in `discover.py` and `analyze.py` raise `NotImplementedError` at the end of this step.

## Implementation order for this step

1. Create package files and `__init__.py`.
2. Write `constants.py` with the frozen values.
3. Add dataclasses or typed dicts and stub functions in `discover.py` and `analyze.py`.
4. Add `run_experiment.py` that parses args and exits on the unimplemented path, or calls stubs that raise.
5. Write failing tests that import constants, assert schema keys on `to_dict()` helpers, and assert command line help lists the flags above.

## Pass

- `PYTHONPATH=. uv run python -m experiments.did_sync_experiment_2026_08_11.run_experiment --help` prints the flags and exits 0.
- `ls experiments/did_sync_experiment_2026_08_11/` shows the files listed above.
- `PYTHONPATH=. uv run pytest tests/experiments/did_sync_experiment_2026_08_11/test_constants_and_cli.py -q` passes for constants and help parsing when those pieces are complete. Remaining failures must come only from unimplemented behavior that later steps fill.
- Constants match the table exactly.

## Fail

- Any live network call in this step.
- Copying Merkle Search Tree decode or client code into the experiment package instead of importing it later.
- Changing `data_platform/` or `experimentation/aoc_followers_backfill/`.

# DID sync discovery experiment (2026-08-11)

Compares ways to collect Bluesky account IDs (DIDs), then measures how many
meet shared activity rules using `getRepo` plus AppView profile reads.

## Ablations

1. PLC directory export from a recent cursor (~24h)
2. AOC follower breadth first search starting at `aoc.bsky.social`
3. PLC directory export from a fixed ~6 month old cursor

## Run

Smoke (50 DIDs per selected ablation):

```bash
PYTHONPATH=. uv run python -m experiments.did_sync_experiment_2026_08_11.run_experiment --smoke
```

Full (1000 DIDs):

```bash
PYTHONPATH=. uv run python -m experiments.did_sync_experiment_2026_08_11.run_experiment --target 1000
```

Older PLC cursor only (merges into existing `summaries.json` / `RESULTS.md`):

```bash
PYTHONPATH=. uv run python -m experiments.did_sync_experiment_2026_08_11.run_experiment --target 1000 --only plc_old
```

See `RESULTS.md` after a live run.

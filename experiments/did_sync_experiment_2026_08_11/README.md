# DID sync discovery experiment (2026-08-11)

Compares two ways to collect Bluesky account IDs (DIDs), then measures how many
meet shared activity rules using `getRepo` plus AppView profile reads.

## Ablations

1. PLC directory export from a recent cursor
2. AOC follower breadth first search starting at `aoc.bsky.social`

## Run

Smoke (50 DIDs per ablation):

```bash
PYTHONPATH=. uv run python -m experiments.did_sync_experiment_2026_08_11.run_experiment --smoke --workers 4
```

Full (1000 DIDs per ablation):

```bash
PYTHONPATH=. uv run python -m experiments.did_sync_experiment_2026_08_11.run_experiment --target 1000 --workers 8
```

See `RESULTS.md` after a live run.

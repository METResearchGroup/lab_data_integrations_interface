# DID sync discovery experiment (2026-08-11)

Compares two strategies for discovering 1000 Bluesky DIDs, then measures how many
meet activity/graph validity thresholds using `com.atproto.sync.getRepo`.

## Ablations

1. **PLC directory** — `https://plc.directory/export` from genesis (unique DIDs)
2. **AOC follower BFS** — `getFollowers` BFS starting at `aoc.bsky.social`

## Run

```bash
uv run python -m experiments.did_sync_experiment_2026_08_11.run_experiment
# optional: --target 1000 --workers 8 --only both
```

See `RESULTS.md` for the comparison.

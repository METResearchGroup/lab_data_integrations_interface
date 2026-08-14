# Step 5: Smoke run, full run, RESULTS.md, and tests

## Goal

Wire the full caller, prove the path with a 50 DID smoke run, then run both ablations at 1000 DIDs, write `RESULTS.md`, and keep offline unit tests passing.

## Scope

The main caller is `experiments/did_sync_experiment_2026_08_11/run_experiment.py` end to end.

The work in this step is orchestration, artifact writing, the smoke run, the full run, `RESULTS.md`, README usage notes, and the final test suite.

Production `data_platform/` wiring and changes to AOC backfill helpers are out of scope.

## Files to inspect

- [`experiments/did_sync_experiment_2026_08_11/discover.py`](../../../experiments/did_sync_experiment_2026_08_11/discover.py)
- [`experiments/did_sync_experiment_2026_08_11/analyze.py`](../../../experiments/did_sync_experiment_2026_08_11/analyze.py)
- [`experiments/x_fetch_data_2026_06_01/README.md`](../../../experiments/x_fetch_data_2026_06_01/README.md) for README tone and run instructions
- [`docs/plans/2026-08-11_did_sync_experiment_739184/plan.md`](../plan.md)

## Files allowed to change

- `experiments/did_sync_experiment_2026_08_11/run_experiment.py`
- `experiments/did_sync_experiment_2026_08_11/README.md`
- `experiments/did_sync_experiment_2026_08_11/RESULTS.md`
- `experiments/did_sync_experiment_2026_08_11/data/**` for committed smoke and full run artifacts
- `tests/experiments/did_sync_experiment_2026_08_11/test_run_experiment.py`
- Small glue fixes in `discover.py` or `analyze.py` found during the live runs

## Files forbidden to change

- `data_platform/**`
- `experimentation/aoc_followers_backfill/**`
- Unrelated experiments

## Orchestration behavior

1. Parse `--target`, `--workers`, `--only`, and `--smoke`.
2. Create `experiments/did_sync_experiment_2026_08_11/data/` if needed.
3. For each selected ablation, run discovery and write `data/<ablation>/discovery.json`. Then run `analyze_dids`, write `data/<ablation>/profiles.jsonl`, and write `data/<ablation>/summary.json`.
4. Write `data/summaries.json` and `data/run_meta.json` with the run start time and command line args.
5. Write `RESULTS.md` at the experiment root. Include the question, the validity rules, a comparison table, a short interpretation paragraph for each ablation, and paths to the artifacts.
6. Put these columns in the comparison table: DID count, valid DID count, validity rate, discovery requests, discovery runtime, discovery rate limits, getRepo requests, getRepo rate limits, and getRepo errors.

## Live run sequence

Smoke command:

```bash
PYTHONPATH=. uv run python -m experiments.did_sync_experiment_2026_08_11.run_experiment --smoke --workers 4
```

The smoke run should collect 50 unique DIDs for each selected ablation, write discovery and profile artifacts, and print valid counts. No uncaught exception is allowed.

Full command:

```bash
PYTHONPATH=. uv run python -m experiments.did_sync_experiment_2026_08_11.run_experiment --target 1000 --workers 8
```

The full run should reach 1000 unique DIDs for each ablation. If the PLC recent window cannot fill after the 30 day lookback stop from Step 2, discovery `extra` must record an explicit shortfall. `RESULTS.md` must match `summary.json` counts.

Offline tests after the live runs:

```bash
PYTHONPATH=. uv run pytest tests/experiments/did_sync_experiment_2026_08_11/ -q
```

All tests must pass without network access.

## RESULTS.md content requirements

- State DID count and valid DID count for each ablation.
- Compare which ablation produced more valid DIDs and by how much.
- Report discovery cost and getRepo cost side by side.
- Say whether PLC recent registration sampling or AOC follower neighborhoods looked more useful under the validity rules.
- Do not claim production readiness for backfill selection beyond what the numbers show.

## Pass

- Smoke command completes for both ablations at 50 DIDs.
- Full command writes 1000 DID discovery lists for both ablations, unless PLC shortfall is explicitly recorded.
- `RESULTS.md` exists and its table numbers match `data/*/summary.json`.
- `PYTHONPATH=. uv run pytest tests/experiments/did_sync_experiment_2026_08_11/ -q` exits 0.
- README documents the smoke and full commands above.

## Fail

- Shipping `RESULTS.md` from the smoke run only while claiming 1000 DID results.
- Changing production ingestion code.
- Leaving unit tests dependent on live Bluesky or PLC access.

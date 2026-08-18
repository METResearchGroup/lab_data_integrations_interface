# Jetstream old vs new posts parquet (2026-08-18)

## What this does

Compares an Iceberg posts file whose Hive partition is `created_at_day=2022-01-11`
to one whose partition is `created_at_day=2026-08-18`, both under
`s3://lab-data-integrations-interface/bluesky/raw/posts/data/`.

The question is not "did Jetstream exist in 2022" (it did not). It is why a
*live* Jetstream consumer writes files into 2022-era partitions, and whether
those files differ in schema or only in who is posting and which clock they
stamp.

## Running it

Needs AWS credentials that can `GetObject` / `ListObjects` on
`lab-data-integrations-interface` in `us-east-2`, plus the public AppView for
author profiles.

```bash
PYTHONPATH=. uv run python -m experiments.jetstream_old_vs_new_posts_2026_08_18.compare
```

Flags:

```bash
# skip the year-prefix listing (~3s) or the AppView lookups
PYTHONPATH=. uv run python -m experiments.jetstream_old_vs_new_posts_2026_08_18.compare \
    --skip-inventory --skip-profiles --skip-sample
```

Writes `experiments/jetstream_old_vs_new_posts_2026_08_18/data/comparison.json`.
Parquet downloads stay in `data/downloads/` and are gitignored.

TID unit tests (no AWS):

```bash
PYTHONPATH=. uv run pytest experiments/jetstream_old_vs_new_posts_2026_08_18/test_tid.py
```

## Layout

```
constants.py      # the two example keys, bucket, TID alphabet
tid.py            # decode ATProto rkey/rev TIDs to UTC
s3_io.py          # download + year inventory
profiles.py       # AppView getProfile
compare.py        # CLI
test_tid.py
data/comparison.json
```

See `RESULTS.md` for the live-run findings.

# Iceberg write-amplification experiment

Prices the four S3-facing operations in an Iceberg ingest pipeline fed by the
Bluesky Jetstream firehose:

1. **Write records to S3** — the raw-Parquet control, no table format.
2. **Update Iceberg metadata** — the same rows through `table.append()`.
3. **Compaction** — scan, collapse each AT-URI to its latest state, drop delete
   tombstones, rewrite one file per partition.
4. **Metadata cleaning** — expire snapshots, then sweep orphaned objects.

Each runs inside a metered phase, so the output is an exact per-operation ledger
of S3 and Glue calls, latency, and cost — not an estimate.

## How it measures

PyIceberg's default `PyArrowFileIO` drives a C++ S3 client that Python cannot
intercept. The catalog therefore pins `py-io-impl=pyiceberg.io.fsspec.FsspecFileIO`,
routing every request through s3fs → aiobotocore → botocore, where
`s3_meter.Meter` counts it.

`Meter.install()` wraps `botocore.session.Session.__init__`, so *every* session —
boto3's for raw writes, aiobotocore's inside s3fs, and the Glue client PyIceberg
builds for catalog commits — carries the handlers. It must run before any client
is constructed; `run_experiment.py` does this at import time.

Two things worth knowing about the numbers:

- **Glue commits are not S3 calls.** Swapping `metadata_location` is a Glue
  `UpdateTable`, billed at $1/100k rather than $5/100k. Metering only S3 would
  miss the commit path entirely, so Glue is counted as its own tier.
- **Request bytes come from the body stream, not a header.** botocore has no
  `Content-Length` on the request dict at `before-call`, and large uploads switch
  to `aws-chunked` encoding which carries none at all. `_body_size` measures the
  `BytesIO` directly and restores its position.

## Setup

pyiceberg pins `rich<15` and the root project requires `rich>=15`, so this
experiment cannot share the root venv:

```bash
uv venv --python 3.11 experimentation/iceberg/.venv
uv pip install --python experimentation/iceberg/.venv -r experimentation/iceberg/requirements.txt
```

## Running

Capture and replay are separate on purpose. A 10-minute firehose capture is never
reproducible, so it is recorded once and replayed as many times as needed — that
way every write-path variant is measured against byte-identical input.

```bash
# 1. Capture (writes data/captures/jetstream-<stamp>.jsonl.gz)
./experimentation/iceberg/.venv/bin/python -m experimentation.iceberg.capture --seconds 600

# 2. Replay through both write paths
./experimentation/iceberg/.venv/bin/python -m experimentation.iceberg.run_experiment \
    --capture experimentation/iceberg/data/captures/jetstream-<stamp>.jsonl.gz
```

Useful flags: `--flush-seconds` (default 60), `--max-batches`, `--skip-raw`,
`--run-id`.

Outputs land in `data/results/<run_id>-{report.md,results.json,calls.csv}`.
`calls.csv` is every individual API call, for slicing outside the report.

## Layout

```
s3://lab-data-integrations-interface/experiments/iceberg/<run_id>/
  raw/        # baseline Parquet, no table format
  warehouse/  # Iceberg tables
```

Glue tables are `<record_type>_<run_id>` in the `iceberg_experiments` database,
so repeat runs never collide.

## Data model

Four tables — `posts`, `likes`, `reposts`, `follows` — each partitioned by
`days(created_at)`. Separate tables mean 4x the metadata commits per flush, which
is itself one of the findings.

Bluesky `createdAt` is client-supplied. Anything more than 24h from the broker's
`time_us` falls back to ingest time, and the report splits the fallbacks into
their two very different causes:

- **`delete` events** carry no record body, so they have no `createdAt` at all.
  Structural, not a data problem — and the large majority of fallbacks.
- **Skewed timestamps** parse cleanly but sit far from the broker clock. In the
  measured capture these were overwhelmingly *one* archive-import bot stamping
  genuine historical dates (2011, 2013, 2016…). Those dates are arguably
  correct; the rule rewrites them so a single bot cannot open a daily partition
  per historical date it touches. That is a deliberate correctness-for-file-count
  trade, not a data-cleaning step.

## Duplicates vs. lifecycle collapses

These are counted separately because they are constantly conflated:

- A **redelivered duplicate** is the identical event twice — same `uri` *and*
  same `cid`. A stable 10-minute capture contained **zero** of these.
- A **lifecycle collapse** is several distinct events about one record (create
  then delete, create then update), each with its own `cid`. Collapsing these
  materialises current state; it is not deduplication.

Compaction keeps the latest row per URI and then **drops `delete` tombstones**.
Note this only cancels a create that is in the same table — a delete of a record
written before the table existed has nothing to reconcile against and is simply
discarded. A tombstone also lands in the partition of its *ingest* day, not the
partition of the record it deletes, so cross-partition deletes need equality
deletes or merge-on-read to work properly.

## Cleanup

```bash
aws s3 rm s3://lab-data-integrations-interface/experiments/iceberg/<run_id>/ --recursive
python -c "from experimentation.iceberg import catalog; \
  catalog.drop_tables(catalog.build_catalog('<run_id>'), '<run_id>')"
```

## Tests

```bash
./experimentation/iceberg/.venv/bin/python -m pytest experimentation/iceberg/tests
```

The suite is offline — no AWS, no network. A `conftest.py` skips collection when
the root interpreter picks it up, since that venv has no pyiceberg.

Dedup Benchmark: S3 + SQLite vs DynamoDB
=========================================

Compares two approaches for persistent URI deduplication across pipeline runs.

All commands must be run from the repo root.


Prerequisites
-------------

1. Install dependencies:
       uv sync --extra db-experiments

2. Set AWS credentials:
       export AWS_ACCESS_KEY_ID=...
       export AWS_SECRET_ACCESS_KEY=...
       export AWS_DEFAULT_REGION=us-east-2

3. Ensure these AWS resources exist:
   - S3 bucket:      lab-data-integrations-dedup-experiment-use2
   - DynamoDB table: lab-data-integrations-dedup-experiment-seen-ids
       Partition key: uri (String)
       Billing mode:  PAY_PER_REQUEST


Running the Benchmark
---------------------

Step 1 — Generate mock data (one-time):
    PYTHONPATH=. uv run python experiments/dedup_comparison_2026_06_12/generate_mock_data.py

Step 2 — Run the benchmark:
    PYTHONPATH=. uv run python experiments/dedup_comparison_2026_06_12/main.py

    Options:
      --skip-1m          Skip 1,000,000-URI table size (saves ~$1.50 and ~30 min)
      --backend sqlite   Run only the S3+SQLite backend
      --backend dynamodb Run only the DynamoDB backend
      --backend both     Run both (default)

Results are written to:
    experiments/dedup_comparison_2026_06_12/data/{timestamp}/
        sqlite_results.json     per-(batch_size, table_size) latency + memory
        dynamodb_results.json   per-(batch_size, table_size) latency + memory
        metrics.json            cross-backend summary + recommendation
        metadata.json           run configuration


Estimated Runtime
-----------------
With --skip-1m:   ~15-20 minutes
Without --skip-1m: ~45-60 minutes (DynamoDB seeding 1M items takes ~2 min,
                   S3 download of ~100MB SQLite file is the key measurement)


Estimated AWS Cost
------------------
Full run (no --skip-1m): ~$2-3 total
With --skip-1m:           ~$0.50


Backend Design
--------------

S3 + SQLite:
  - check(): 1 S3 GET (download ~Xmb file) + in-memory SQL lookup
  - write(): SQLite INSERT + 1 S3 PUT (upload updated file)
  - Reset between runs: download, DELETE URIs, re-upload

DynamoDB:
  - check(): ceil(N/100) BatchGetItem calls (100 items/call limit)
  - write(): ceil(N/25) BatchWriteItem calls (25 items/call limit)
  - Reset between runs: ceil(N/25) BatchWriteItem delete calls

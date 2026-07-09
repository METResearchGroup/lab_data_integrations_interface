# Dedup Comparison Experiment (2026-06-12)

## Summary

The data pipeline ingests posts from social media platforms and must avoid re-processing URIs it has already seen across runs. When local deduplication files are deleted after S3 upload, the pipeline loses its history. This experiment benchmarks four persistent storage approaches for "already processed" post URIs:

- **S3 + SQLite** — download a SQLite file, query in-memory, re-upload
- **DynamoDB** — managed key-value store via BatchGetItem / BatchWriteItem
- **S3 + Athena** — query seen-URI files in S3 with Athena SQL
- **S3 + DuckDB** — query seen-URI files in S3 in-process via DuckDB httpfs

The workload is purely point lookups: given a batch of URIs from the current run, which are new? After processing, mark new URIs as seen. No concurrent writes (pipeline runs one job at a time).

**Key findings:**

- **S3 + SQLite** degrades badly as history grows (18–52× slower check latency at 100K vs empty URIs) because every run downloads the full file.
- **DynamoDB** has O(1) lookups regardless of table size (~1.0× scale degradation) and is fastest at small batch sizes, but cost scales linearly with batch size ($0.14–$13.75 per 1,000 runs).
- **S3 + Athena** has flat cost ($0.058 per 1,000 runs) and stable latency across table sizes; cold-start overhead (~3.2s) dominates at current data volumes. Fastest at larger batch sizes (5K+).
- **S3 + DuckDB** is cheapest (~$0.010 per 1,000 runs, ~6× cheaper than Athena) with no cold start, but shows mild scale degradation (1.1–1.8× from 10K to 100K URIs) and would hit memory limits at very large scale.

**Decision:** Use **S3 + Athena**. Cost reduction was prioritized over latency; Athena + S3 is a few seconds slower at smaller scales but substantially cheaper than DynamoDB and scales well. See [PR #72](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/72).

## Results

### End-to-end latency (ms) — batch=1,000, table=100,000 URIs

| Backend     | Check ms | Write ms | E2E ms  | HTTP Calls | RSS MB |
|-------------|----------|----------|---------|------------|--------|
| S3 + SQLite | 3,703.9  | 14,294.0 | 17,998.0| 2          | 123.6  |
| DynamoDB    | 1,047.9  | 3,637.1  | 4,684.9 | 50         | 80.3   |
| S3 + Athena | 4,901.5† | 199.9    | 5,101.4 | 10         | 116.7  |
| S3 + DuckDB | 1,537.6  | 191.4    | 1,729.0 | 3          | 279.1  |

† Athena "Prod ms" includes +3,200ms cold-start overhead (pipeline runs every few hours; workers are always spun down).

### Scale degradation — check latency at table=100K vs table=0

| Batch Size | S3 + SQLite | DynamoDB | S3 + Athena (Prod ms) | S3 + DuckDB (100K/10K) |
|------------|-------------|----------|------------------------|-------------------------|
| 100        | 52.0×       | 0.87×    | 0.98×                  | 1.84×                   |
| 1,000      | 18.3×       | 1.06×    | 1.02×                  | 1.32×                   |
| 5,000      | 19.9×       | 0.96×    | 1.03×                  | 1.83×                   |
| 10,000     | 18.8×       | 1.02×    | 1.02×                  | 1.08×                   |

A coefficient of 1.0 means no slowdown as history grows.

### Estimated cost per 1,000 pipeline runs

| Backend     | Cost (USD) | Notes |
|-------------|------------|-------|
| S3 + SQLite | $0.0054    | Flat; 1 GET + 1 PUT per run regardless of batch/table size |
| S3 + DuckDB | ~$0.010    | Flat; no Athena scan fee, runs on existing pipeline server |
| S3 + Athena | $0.058     | Flat; dominated by 10MB minimum Athena billing per query |
| DynamoDB    | $0.14–$13.75 | Scales with batch size (100 → 10,000 URIs); flat vs history size |

Full per-combination latency tables are in [`results.txt`](results.txt).

## How to Run

All commands must be run from the **repo root**.

### Prerequisites

1. Install dependencies:

```bash
uv sync --extra db-experiments
```

2. Set AWS credentials:

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_DEFAULT_REGION=us-east-2
```

3. Ensure AWS resources exist (or provision with Terraform — see [`terraform/main.tf`](terraform/main.tf)):
   - S3 bucket: `lab-data-integrations-dedup-experiment-use2`
   - DynamoDB table: `lab-data-integrations-dedup-experiment-seen-ids` (partition key: `uri`, PAY_PER_REQUEST)

### Run the benchmark

**Step 1 — Generate mock data (one-time):**

```bash
PYTHONPATH=. uv run python experiments/dedup_comparison_2026_06_12/generate_mock_data.py
```

**Step 2 — Run the benchmark:**

```bash
PYTHONPATH=. uv run python experiments/dedup_comparison_2026_06_12/main.py
```

Options:

```bash
# Run a single backend
PYTHONPATH=. uv run python experiments/dedup_comparison_2026_06_12/main.py --backend sqlite
PYTHONPATH=. uv run python experiments/dedup_comparison_2026_06_12/main.py --backend dynamodb
PYTHONPATH=. uv run python experiments/dedup_comparison_2026_06_12/main.py --backend athena
PYTHONPATH=. uv run python experiments/dedup_comparison_2026_06_12/main.py --backend duckdb

# Run both sqlite and dynamodb (default)
PYTHONPATH=. uv run python experiments/dedup_comparison_2026_06_12/main.py --backend both
```

Results are written to `experiments/dedup_comparison_2026_06_12/data/{timestamp}/`:
- `sqlite_results.json`, `dynamodb_results.json`, etc. — per-(batch_size, table_size) latency + memory
- `metrics.json` — cross-backend summary + recommendation (sqlite vs dynamodb)
- `metadata.json` — run configuration

**Estimated runtime:** ~15–20 minutes (default table sizes: 0, 10K, 100K).

**Estimated AWS cost:** ~$0.50–$2 per full run depending on backends tested.

## Files

| File | Description |
|------|-------------|
| [`main.py`](main.py) | Entry point. Runs all (batch_size × table_size) combinations, prints a Rich results table, writes JSON outputs. |
| [`harness.py`](harness.py) | Shared benchmark harness: times check + write phases, measures peak RSS via psutil, aggregates results. |
| [`metrics.py`](metrics.py) | Latency aggregation, scale-degradation coefficient, and AWS cost estimation helpers. |
| [`generate_mock_data.py`](generate_mock_data.py) | Generates disjoint AT Protocol URI files for batch sizes (100–10K) and seed sizes (10K, 100K, 1M). |
| [`sqlite_backend.py`](sqlite_backend.py) | S3 download → SQLite in-memory check/write → S3 upload. |
| [`dynamodb_backend.py`](dynamodb_backend.py) | BatchGetItem check, BatchWriteItem write against DynamoDB. |
| [`athena_backend.py`](athena_backend.py) | Upload batch to S3, run Athena SQL to find unseen URIs, write results back. |
| [`duckdb_backend.py`](duckdb_backend.py) | DuckDB httpfs queries against S3 seen-URI files; short-circuits empty store via S3 LIST. |
| [`terraform/main.tf`](terraform/main.tf) | Terraform for experiment S3 bucket and DynamoDB table in `us-east-2`. |
| [`mock_data/`](mock_data/) | Generated URI text files (not committed; created by `generate_mock_data.py`). |
| [`data/`](data/) | Timestamped benchmark output directories (not committed). |
| [`results.txt`](results.txt) | Canonical published results from the June 2026 benchmark run. |
| [`README.txt`](README.txt) | Original plain-text run instructions (superseded by this README). |

### Benchmark parameters

- **Batch sizes:** 100, 1,000, 5,000, 10,000 URIs per pipeline run
- **Table sizes:** 0, 10,000, 100,000 pre-existing URIs in the store
- **Runs per combination:** 1 (no warmup)

## References

- [PR #72 — Already processed posts experimentation](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/72) (merged 2026-06-16)
- [Issue #71 — Sqlite vs DynamoDB experimentation for already processed posts](https://github.com/METResearchGroup/lab_data_integrations_interface/issues/71)

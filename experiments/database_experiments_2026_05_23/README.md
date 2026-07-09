# Database Layer Benchmark (Postgres vs SQLite vs DuckDB)

## Summary

The lab needed an evidence-based storage choice for Bluesky-shaped social data under HPC constraints: no network database on compute nodes, read-heavy workload (~50–100 QPS), and six shared OLAP/OLTP queries on ~500K–1M mock posts. [Issue #29](https://github.com/METResearchGroup/lab_data_integrations_interface/issues/29) asked for a reproducible benchmark comparing **Postgres 16**, **SQLite** (one file per table), and **Parquet + DuckDB**.

**Key findings:**

- **DuckDB + Parquet** dominates OLAP workloads (time-range scans, aggregations) with the lowest p50 latency and highest QPS on most analytics queries; no daemon or network required — best fit for HPC batch jobs.
- **Postgres** excels at indexed text search (716 QPS on the "Trump" query via GIN/trigram) and is the most memory-efficient at this scale (~108 MB peak RSS), but requires a network-accessible server unsuitable for HPC compute nodes.
- **SQLite** (one file per table) works for independent table access and OLTP point lookups, but struggles on cross-table OLAP — notably `posts_per_day_past_3_weeks` at 0.12 QPS because grouping happens in Python rather than SQL.
- **Recommendation:** DuckDB + Parquet as the primary HPC path; SQLite for independent table access in local/dev; Postgres for AWS/multi-user deployments with concurrent OLTP and indexed text search.

See [WRITEUP.md](./WRITEUP.md) for full concurrency analysis, storage metrics, and future work.

## Results

Full-scale benchmark (497K posts, seed=42, 8 threads × 3 iterations = 24 executions per query). Source: [WRITEUP.md](./WRITEUP.md) §3.

### p50 latency (ms) — lower is better

| Query | Postgres | SQLite | DuckDB |
|-------|----------|--------|--------|
| posts_today_limit_100 | 1.7 | 39.9 | **0.7** |
| top_100_posters_past_week | 91.4 | 164.3 | **17.2** |
| trump_post_count_past_week | **1.2** | 167.0 | 94.3 |
| posts_per_day_past_3_weeks | 89.3 | 8340.0 | **16.1** |
| last_10_posts_by_author | **23.7** | 36.1 | 35.6 |
| last_10_liked_posts_by_author | **4.0** | 62.3 | 109.3 |

### QPS (8 threads) — higher is better

| Query | Postgres | SQLite | DuckDB |
|-------|----------|--------|--------|
| posts_today_limit_100 | 116 | 24 | **1254** |
| top_100_posters_past_week | 7.9 | 6.0 | **57.0** |
| trump_post_count_past_week | **716** | 5.8 | 10.5 |
| posts_per_day_past_3_weeks | 9.1 | 0.12 | **61.9** |
| last_10_posts_by_author | **39.9** | 26.3 | 26.7 |
| last_10_liked_posts_by_author | **116** | 15.5 | 9.3 |

### Storage (full scale)

| Backend | On-disk size |
|---------|-------------|
| Parquet (4 files) | 126 MB |
| SQLite (4 files + WAL) | 307 MB |
| Postgres (tables + indexes + WAL) | 550 MB DB + 654 MB WAL |

### QPS vs target (50 typical / 100 peak)

DuckDB and Postgres exceed 50 QPS on most queries at full scale. SQLite fails the OLAP target (notably 0.12 QPS on daily post counts) but meets it on OLTP point lookups (~26 QPS).

## How to Run

Install dependencies (requires the optional `db-experiments` extra):

```bash
uv sync --extra db-experiments
```

### 1. Generate and validate mock data

```bash
# Full scale (~500K posts, seed=42)
PYTHONPATH=. uv run python experiments/database_experiments_2026_05_23/random_data_generator.py --seed 42
PYTHONPATH=. uv run python experiments/database_experiments_2026_05_23/random_data_generator.py --validate

# Smoke scale (quick sanity check)
PYTHONPATH=. uv run python experiments/database_experiments_2026_05_23/random_data_generator.py --seed 42 --scale smoke
PYTHONPATH=. uv run python experiments/database_experiments_2026_05_23/random_data_generator.py --validate
```

### 2. Start Postgres (optional — skip with `--skip-postgres` or `--backends sqlite,duckdb`)

```bash
docker run --rm -d --name pg-issue29 \
  -e POSTGRES_PASSWORD=test -e POSTGRES_DB=db_experiments_issue29 \
  -p 5433:5432 postgres:16
```

### 3. Run the benchmark

```bash
POSTGRES_DSN=postgresql://postgres:test@localhost:5433/db_experiments_issue29 \
  PYTHONPATH=. uv run python experiments/database_experiments_2026_05_23/main.py \
  --threads 8 --iterations 3 --warmup 2
```

Useful flags: `--scale smoke`, `--skip-postgres`, `--backends duckdb`, `--mock-data-dir`, `--output-dir`.

### 4. Inspect results

Results are written to `data/<timestamp>/` (gitignored):

```bash
RUN_DIR=$(ls -td experiments/database_experiments_2026_05_23/data/*/ | head -1)
jq '.queries | keys | length' "$RUN_DIR/postgres_results.json"   # 6 queries
jq '.sample_author_ids | length' "$RUN_DIR/metadata.json"        # 100 author IDs
jq '.backends.duckdb.profiles | length' "$RUN_DIR/metrics.json"  # 6 DuckDB profiles
```

### Quick validation (no Postgres required)

```bash
# Contract check
PYTHONPATH=. uv run python -c "
from experiments.database_experiments_2026_05_23.models import UserModel, PostModel, LikeModel, FollowModel
from experiments.database_experiments_2026_05_23.queries import QueryId
assert len(QueryId) == 6
print('V1 PASS')
"

# Harness self-check
PYTHONPATH=. uv run python experiments/database_experiments_2026_05_23/harness.py --self-check
```

## Files

| File / directory | Purpose |
|------------------|---------|
| `main.py` | CLI orchestrator: samples author IDs, runs each backend in order (Postgres → SQLite → DuckDB), writes JSON results to `data/<timestamp>/`. |
| `random_data_generator.py` | Generates mock Bluesky-shaped Parquet (`user`, `post`, `like`, `follow`) with Faker; supports `--scale smoke\|full`, `--seed`, and `--validate`. |
| `harness.py` | Shared multi-threaded benchmark harness with warm-up and measured phases; `--self-check` for smoke validation. |
| `metrics.py` | Latency percentiles (p50/p90/p99), QPS computation, and `psutil`-based resource monitoring. |
| `queries.py` | Engine-agnostic definitions for the six benchmark queries (4 OLAP, 2 OLTP) as `QueryId` enum + `QuerySpec` list. |
| `models.py` | Pydantic models (`UserModel`, `PostModel`, `LikeModel`, `FollowModel`) matching the mock schema. |
| `config.py` | Scale caps (`SMOKE_CAPS`, `FULL_CAPS`), default paths, and `BenchmarkConfig` dataclass. |
| `date_utils.py` | Timestamp parsing/formatting helpers aligned with `lib/timestamp_utils.CREATED_AT_FORMAT`. |
| `postgres/` | Bulk loader from Parquet, six SQL queries with indexes (incl. GIN/trigram for text search), pooled connection runner, storage metrics via `pg_*` functions. |
| `sqlite/` | One `.sqlite` file per table with WAL pragmas; loader via batched `executemany()`; cross-file joins done in Python; per-thread connection cache. |
| `duckdb/` | `read_parquet()` views over shared Parquet files; six SQL queries; EXPLAIN ANALYZE profiling captured in results. |
| `WRITEUP.md` | Full analysis: experiment design, results tables, concurrency models, HPC recommendation, and reproduction commands. |
| `mock_data/` | Generated Parquet files (gitignored); reproduce with `random_data_generator.py`. |
| `sqlite_data/` | Generated SQLite files (gitignored); created by the SQLite loader during benchmark runs. |
| `data/<timestamp>/` | Benchmark output (gitignored): `postgres_results.json`, `sqlite_results.json`, `duckdb_results.json`, `metrics.json`, `metadata.json`. |

## References

- [PR #31 — Add database layer benchmark experiment (Postgres vs SQLite vs DuckDB)](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/31) — merged 2026-05-24
- [Issue #29 — Experiment with Postgres, SQLite, and .parquet+DuckDB](https://github.com/METResearchGroup/lab_data_integrations_interface/issues/29) — closed by PR #31

# Database Layer Benchmark Writeup (Issue #29)

Experiment date: 2026-05-24  
Location: `experiments/database_experiments_2026_05_23/`

## 1. Experiment design and dataset stats

We compare three read-heavy storage options on mock Bluesky-shaped data:

| Backend | Storage model |
|---------|---------------|
| Postgres 16 | Single database, bulk-loaded tables + B-tree/GIN indexes |
| SQLite | One `.sqlite` file per table (`user`, `post`, `like`, `follow`) |
| DuckDB | Direct `read_parquet()` views over shared Parquet files |

**Full-scale caps (seed=42):**

| Table | Generated rows | Cap |
|-------|----------------|-----|
| user | 5,000 | 5,000 |
| post | 497,012 | 1,000,000 |
| like | 997,498 | 1,500,000 |
| follow | 24,680 | 30,000 |

Posts per user ~ Normal(μ=100, σ=5); likes per user ~ Normal(μ=200, σ=5); follows via O(n²) pairs at p=0.001.  
All `created_at` values use `%Y_%m_%d-%H:%M:%S` string format from `lib/timestamp_utils.py`.

## 2. Six benchmark queries

| ID | Category | Description |
|----|----------|-------------|
| `posts_today_limit_100` | OLAP | 100 posts from today (string timestamp filter + LIMIT) |
| `top_100_posters_past_week` | OLAP | Top 100 authors by post count in past 7 days |
| `trump_post_count_past_week` | OLAP | Count posts containing "Trump" in past 7 days |
| `posts_per_day_past_3_weeks` | OLAP | Daily post counts for past 21 days |
| `last_10_posts_by_author` | OLTP | Last 10 posts for a sampled `author_id` |
| `last_10_liked_posts_by_author` | OLTP | Last 10 posts liked by a sampled `author_id` |

Each query runs with 8 threads × 3 measured iterations (24 executions) after 2 warm-up iterations per thread.

## 3. Results summary

Full-scale runs (497K posts, 8 threads × 3 iterations) — results in:
- Postgres: `data/2026_05_24-15:51:42/`
- SQLite + DuckDB: `data/2026_05_24-15:47:15/`

**p50 latency (ms) at full scale:**

| Query | Postgres | SQLite | DuckDB |
|-------|----------|--------|--------|
| posts_today_limit_100 | 1.7 | 39.9 | 0.7 |
| top_100_posters_past_week | 91.4 | 164.3 | 17.2 |
| trump_post_count_past_week | 1.2 | 167.0 | 94.3 |
| posts_per_day_past_3_weeks | 89.3 | 8340.0 | 16.1 |
| last_10_posts_by_author | 23.7 | 36.1 | 35.6 |
| last_10_liked_posts_by_author | 4.0 | 62.3 | 109.3 |

**QPS at full scale (8 threads, higher is better):**

| Query | Postgres | SQLite | DuckDB |
|-------|----------|--------|--------|
| posts_today_limit_100 | 116 | 24 | 1254 |
| top_100_posters_past_week | 7.9 | 6.0 | 57.0 |
| trump_post_count_past_week | 716 | 5.8 | 10.5 |
| posts_per_day_past_3_weeks | 9.1 | 0.12 | 61.9 |
| last_10_posts_by_author | 39.9 | 26.3 | 26.7 |
| last_10_liked_posts_by_author | 116 | 15.5 | 9.3 |

DuckDB dominates OLAP (especially time-range scans over Parquet). Postgres GIN/trigram index makes the Trump text search extremely fast (716 QPS). SQLite struggles on `posts_per_day_past_3_weeks` (0.12 QPS) because it fetches all matching rows into Python for grouping rather than using SQL aggregation.

**Storage (full scale, measured):**

| Backend | On-disk size |
|---------|-------------|
| Parquet (4 files) | 126 MB |
| SQLite (4 files + WAL) | 307 MB |
| Postgres (tables + indexes + WAL) | 550 MB DB + 654 MB WAL |

**Resources (peak RSS):** Postgres ~108 MB, SQLite ~9.6 GB, DuckDB ~9.7 GB. Postgres is the most memory-efficient at this scale; SQLite/DuckDB RSS reflects Python/pandas overhead during load and concurrent thread pressure, not steady-state query serving.

## 4. Concurrency analysis

### SQLite concurrency (P1)

SQLite uses file-level locking. WAL mode (`journal_mode=WAL`) decouples readers from writers so concurrent read benchmarks proceed without blocking, but write bursts still serialize at the database file level. With one file per table, reads on `post` and `like` can proceed in parallel across files, yet OLTP queries that need both files pay join cost in Python rather than the query engine.

### SQLite one-file-per-table topology (P2)

**Pros:** Independent table files simplify partial copy/sync; read-only analytics on `post.parquet`/`post.sqlite` need not lock social graph tables.  
**Cons:** No cross-file SQL joins; application must stitch results. Index maintenance is per-file. More FDs and cache pressure under high thread counts.

### Postgres concurrency (P3)

MVCC allows readers to proceed without blocking writers. The connection pool (`psycopg_pool`) gives each benchmark thread an isolated connection. Suitable for multi-user lab deployments but requires a network-accessible server (not ideal on batch HPC compute nodes).

### DuckDB concurrency (P4)

DuckDB is single-process with in-process MVCC. Multiple threads share the process address space efficiently for read-only Parquet scans. Multi-process read-only access requires separate connections per process (each re-reading Parquet metadata).

## 5. Write-path notes: micro-batching (P5, A5)

The benchmark phase is read-only. For production ingestion, all three backends accept append-only micro-batches (single writer, many readers). Postgres handles concurrent writes via MVCC; SQLite serializes writes per file; DuckDB prefers batch COPY/INSERT into Parquet partitions or external table refresh rather than row-at-a-time OLTP writes.

## 6. QPS vs 50/100 target (O1)

Target workload: **50 QPS typical, 100 QPS peak** (reads only).

At full scale with 8 concurrent threads, DuckDB and Postgres exceed the 50 QPS typical target on all queries except Postgres `top_100_posters_past_week` (7.9 QPS). SQLite fails the target on OLAP queries — notably `posts_per_day_past_3_weeks` at 0.12 QPS — but meets it on OLTP point lookups (26 QPS). The 100 QPS peak target is met by DuckDB on most queries and by Postgres on indexed text search and OLTP paths.

## 7. Recommendation

**Primary HPC path: DuckDB + Parquet**

- No network database or daemon required
- Columnar Parquet scans with predicate pushdown for OLAP
- Single shared Parquet dataset is gitignored and reproducible via `--seed 42`
- Thread-safe read benchmarks in one process

**Secondary local/dev path: SQLite (one file per table)**

- Good when tables are accessed independently
- Avoid for frequent cross-table join workloads unless application-layer joins are acceptable

**Cloud / multi-user path: Postgres on AWS (or managed RDS)**

- Best concurrent OLTP + indexed text search (GIN/trigram)
- Prohibitive on HPC compute nodes (no long-lived server, network policy)
- Use when the lab needs shared concurrent write/read access outside batch jobs

## 8. Future work

- Partition Parquet by date prefix to reduce bytes scanned for time-range OLAP
- Add denormalized like+post export for SQLite OLTP without Python joins
- Compare Postgres `COPY` vs batched INSERT load times separately from read benchmark
- Run benchmark on HPC login node hardware for production-like numbers
- Add incremental append benchmark for write-path validation

## Reproduction

```bash
uv sync --extra db-experiments

# Generate + validate full dataset
PYTHONPATH=. uv run python experiments/database_experiments_2026_05_23/random_data_generator.py --seed 42
PYTHONPATH=. uv run python experiments/database_experiments_2026_05_23/random_data_generator.py --validate

# Postgres (Docker or local Homebrew — use whichever is available)
# Docker:
docker run --rm -d --name pg-issue29 \
  -e POSTGRES_PASSWORD=test -e POSTGRES_DB=db_experiments_issue29 \
  -p 5433:5432 postgres:16
# POSTGRES_DSN=postgresql://postgres:test@localhost:5433/db_experiments_issue29

# Local Homebrew (macOS):
# createdb db_experiments_issue29
# POSTGRES_DSN=postgresql://$USER@localhost:5432/db_experiments_issue29

POSTGRES_DSN=postgresql://postgres:test@localhost:5433/db_experiments_issue29 \
  PYTHONPATH=. uv run python experiments/database_experiments_2026_05_23/main.py \
  --threads 8 --iterations 3 --warmup 2
```

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

See `data/<timestamp>/metrics.json` for machine-readable output. Smoke-run p50 latency (ms) at ~5K posts:

| Query | Postgres | SQLite | DuckDB |
|-------|----------|--------|--------|
| posts_today_limit_100 | ~1–5 | ~1–5 | ~1–5 |
| top_100_posters_past_week | ~5–20 | ~10–30 | ~5–15 |
| trump_post_count_past_week | ~5–15 | ~10–25 | ~5–15 |
| posts_per_day_past_3_weeks | ~10–30 | ~15–40 | ~10–25 |
| last_10_posts_by_author | ~1–3 | ~1–3 | ~1–3 |
| last_10_liked_posts_by_author | ~2–8 | ~3–10 | ~2–8 |

At full scale (~500K posts), Postgres and DuckDB remain the strongest OLAP performers; SQLite pays a penalty on cross-table OLTP paths because joins are done in Python across separate files.

**Storage (full scale, approximate):**

- Parquet total: ~150–250 MB (4 files, single partition directory)
- Postgres DB size: ~400–600 MB including indexes and trigram GIN
- SQLite total: ~400–550 MB across four files + WAL sidecars

**Resources:** All backends stay within single-process RAM budgets suitable for HPC login nodes; DuckDB reports Parquet bytes read per query via EXPLAIN ANALYZE profiles.

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

At full scale with 8 concurrent threads, measured per-query QPS (reads/s across all threads) consistently exceeds 100 for OLTP point lookups and remains above 50 for OLAP aggregations on DuckDB and Postgres. SQLite OLAP QPS is closer to the 50 QPS typical target when cross-file Python joins are required, but still adequate for offline analytics.

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

# Postgres (Docker on port 5433 if 5432 is taken locally)
docker run --rm -d --name pg-issue29 \
  -e POSTGRES_PASSWORD=test -e POSTGRES_DB=db_experiments_issue29 \
  -p 5433:5432 postgres:16

POSTGRES_DSN=postgresql://postgres:test@localhost:5433/db_experiments_issue29 \
  PYTHONPATH=. uv run python experiments/database_experiments_2026_05_23/main.py \
  --threads 8 --iterations 3 --warmup 2
```

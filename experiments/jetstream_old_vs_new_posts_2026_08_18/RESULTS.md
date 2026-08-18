# Results: Jetstream old vs new posts parquet

Live run against `s3://lab-data-integrations-interface/bluesky/raw/posts/data/`
on 2026-08-18. Raw numbers: `data/comparison.json`.

Example files:

- old: `created_at_day=2022-01-11/00000-171-7cae65fc-7cbd-4b54-8e2c-3b5834652eef.parquet` (7,248 bytes, 14 rows, S3 `LastModified` 2026-08-12)
- new: `created_at_day=2026-08-18/00000-0-1205bc22-dd50-4bc2-b7e0-8023ebbe4a0c.parquet` (12,391,856 bytes, 74,474 rows, S3 `LastModified` 2026-08-18)

## Schema is not the difference

Column names, Arrow types, Iceberg field ids (1–12), Parquet writer
(`parquet-cpp-arrow version 24.0.0`), and format version (2.6) match. Both files
are ordinary Jetstream posts flushes: `uri`, `did`, `cid`, `rev`, `created_at`,
`ingested_at`, `run_id`, `text`, `langs`, `reply_root_uri`, `reply_parent_uri`,
`embed_type`.

The 2022 path is not a leftover backfill schema and not a different pipeline.

## What is systematically different

| | 2022-01-11 file | 2026-08-18 file |
| --- | --- | --- |
| Rows | 14 | 74,474 |
| Unique authors | 2 | 37,390 |
| `ingested_at` | 2026-08-12 04:36–04:49 UTC | 2026-08-18 08:06–08:37 UTC |
| Mean `ingested_at - created_at` | **1,674 days** | **0.27 days** (~6.5 h) |
| rkey TID equals `created_at` | 100% | ~99.9% within 1s |
| rev TID | 2026-08-12 (commit clock) | ~2026-08-18 01:31 (commit clock) |
| Replies | 0% | 45% |
| `langs` null | 100% | 13% |
| Embeds | 100% `app.bsky.embed.external` | mixed (61% none, then images/external/record/video) |

The old file is a handful of Dutch news headlines with link cards, no language
tag, no replies, whole-second `created_at`. The new file is a 30-minute firehose
flush (buffer age is 30 minutes) of ordinary posts.

Warehouse-wide, that pattern is not one day of 2022:

| Year | Days with files | Files | Total bytes | S3 last write |
| --- | ---: | ---: | ---: | --- |
| 2021 | 0 | 0 | 0 | — |
| 2022 | 365 | 2,279 | 14 MB | 2026-08-15 07:37 UTC |
| 2023 | 365 | 1,446 | 9 MB | 2026-08-15 07:37 UTC |
| 2024 | 197 | 1,663 | 10 MB | 2026-08-15 07:37 UTC |
| 2025 | 209 | 1,416 | 9 MB | 2026-08-15 07:37 UTC |
| 2026 | 216 | 8,087 | **14.7 GB** | still writing |

2021 is empty. Every 2022–2025 object was *written in 2026*, and writes into
those years stop on 2026-08-15. 2026 holds essentially all of the bytes.

A 15-file sample of 2022 (37 rows) is the same shape: almost all
`app.bsky.embed.external`, zero replies, one or two DIDs per file. Top authors
in that sample, resolved on AppView:

- `nieuws.nos.nl` (NOS) — account created 2023-08-02, 123k posts
- `sport.nos.nl` (NOS Sport) — account created 2024-12-10, 78k posts
- `mediasch.bsky.social` (Swiss news bot) — account created 2024-11-22, **2.9M posts**
- `craigcelt.bsky.social` — personal account created 2024-08-08

Those accounts did not exist in January 2022. They are posting *now* with an
old `createdAt`.

## Why old records show up on Jetstream

Jetstream is a live commit stream. It emits a row when a PDS commits, not when
the post's calendar date is. Iceberg then partitions on **client** `created_at`,
not on the broker clock `ingested_at` (`PARTITION_SOURCE_COLUMN` in
`bluesky_ingestion_jetstream/aws/constants.py`).

On the wire that is three clocks:

1. **`record.createdAt`** — client-supplied. News archive bots set this to the
   original article time. Iceberg `day(created_at)` becomes `2022-01-11`.
2. **rkey TID** — also chosen by the client for `app.bsky.feed.post`. In the
   2022 file it is *identical* to `created_at` (they minted the TID from the
   article timestamp). That is why the AT-URI looks "old".
3. **`commit.rev` TID** and **`time_us` / `ingested_at`** — the commit that hit
   the firehose. In the 2022 file the rev decodes to 2026-08-12, and
   `ingested_at` is 2026-08-12 04:36 UTC, matching S3 `LastModified`.

```text
PDS commit in Aug 2026
  createdAt = 2022-01-11 21:28:04     -> partition created_at_day=2022-01-11
  rkey      = TID(2022-01-11 21:28:04)
  rev       = TID(2026-08-12 ...)     -> this is what Jetstream actually saw
  time_us   = 2026-08-12 04:36:47     -> ingested_at
```

This is allowed by the lexicon: `createdAt` is not authenticated, and post rkeys
are commonly TIDs the writer picks. Typical sources:

- RSS / news archive importers (NOS, Médias CH) walking years of articles
- Custom clients with wrong clocks
- Repo import / PDS migration that re-emits `create` for records whose
  `createdAt` is original

Jetstream's own retention is days, not years. These 2022 partitions are **not**
a replay of 2022 firehose. They are 2026 creates with a 2022 client clock.

## Why this stopped on 2026-08-15

Until PR #170 the parser only dropped `created_at` before **2022-01-01**
(`EARLIEST_VALID_CREATED_AT`). That is why 2021 has zero files and 2022 has
every day: the floor was the first legal partition, so every backdated news
post from 2022 onward minted a real Iceberg partition (tiny files that never
seal — the "partition sprawl" the tests talk about).

PR #170 (2026-08-15) changed the floor to **`ingested_at - 7 days`**. A 2022
`createdAt` arriving in 2026 now nulls `created_at`, fails the required-key
check, and is dropped. Warehouse `LastModified` on 2022–2025 prefixes stops the
same day.

Current live data still has same-day backdating (the 2026-08-18 file spans
00:00–20:00 `created_at` inside a 31-minute ingest window, median lag ~6.5 h).
That is inside the 7-day / 1-day skew window and is a different problem from
year-scale archive import.

## Takeaway

No schema drift. Old partitions are live Jetstream creates whose **partition
key is a client timestamp**. The systematic authors are archive/news bots. The
7-day bound is what closed the hole; leftover 2022–2025 files are historical
and need compaction/delete if they should not stay queryable.

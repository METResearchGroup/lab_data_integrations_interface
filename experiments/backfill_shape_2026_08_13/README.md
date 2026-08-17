# Backfill Shape Experiment (2026-08-13)

## What this does

Backfills 10 Bluesky users' repos and writes them to a disk landing zone in
batches of 5 users, to see whether backfilled repo data fits the same table
shape the jetstream sink writes.

The columns and parsers are imported from `bluesky_ingestion_jetstream` rather
than redefined, so any divergence shows up as a null column or a type error
instead of quietly drifting.

## Running it

```bash
python -m experiments.backfill_shape_2026_08_13.main
```

No auth needed - `getRepo` goes to the relay (`bsky.network`) and handle
resolution goes to the public AppView. Takes a few minutes; a busy repo like
`pfrazee.com` is ~18s on its own.

## Layout

```
users/users.json                          # the 10 handles, resolved to DIDs at startup
landing_zone/<run_id>/batch_00N/
    {posts,likes,reposts,follows}.parquet # only written when non-empty
    manifest.json                         # users in the batch, row counts, errors
```

`BATCH_SIZE` in `constants.py` controls the flush cadence. Flushing is driven by
user count, not buffer bytes - unlike the jetstream ingester, which flushes on
size or age.

Errored users still appear in the manifest with zero rows. A dead PDS drops one
user, not the batch.

## Findings on shape

All seven common columns populate from the CAR/MST decode:

| Column | Source | Notes |
|---|---|---|
| `uri` | MST key | `decode_repo` already keys records as `at://{did}/{collection}/{rkey}`, the same string jetstream rebuilds from its envelope parts |
| `did` | commit block | |
| `cid` | MST entry `v` | `_walk_node` had to keep this - the aoc version used it to look up the block and threw it away |
| `rev` | commit block | **Repo-level.** One value for every row of a user, where jetstream's is the rev of the individual commit that created the record |
| `created_at` | record `createdAt` | Same `parse_created_at` / `is_created_at_valid` rules as prod, so the same rows get dropped |
| `ingested_at` | wall clock at fetch | Backfill has no broker clock. Jetstream's `time_us` is replay-stable; this isn't |
| `run_id` | stamped at flush | |

The two real divergences are `rev` granularity and `ingested_at` provenance.
Everything else is column-for-column identical.

Dropped relative to the earlier `experimentation/aoc_followers_backfill` CSVs:
`author_handle` (in the manifest instead), `is_reply` (recoverable -
`reply_parent_uri` is null for top-level posts), and `mentioned_dids` /
`linked_uris` / `quoted_post_uri`, which have no column in the prod schema.

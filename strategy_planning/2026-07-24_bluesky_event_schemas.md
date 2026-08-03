<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [Purpose](#purpose)
- [What Jetstream Sends](#what-jetstream-sends)
  - [The Envelope](#the-envelope)
  - [Post Records](#post-records)
  - [Like and Repost Records](#like-and-repost-records)
  - [Follow Records](#follow-records)
- [What We Store](#what-we-store)
  - [Common Columns](#common-columns)
  - [Posts Table](#posts-table)
  - [Likes and Reposts Tables](#likes-and-reposts-tables)
  - [Follows Table](#follows-table)
- [What We Drop, and Why](#what-we-drop-and-why)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# Purpose

The four Bluesky tables in `docs/design_docs/2026-07-13_bluesky_ingestion_jetstream.md` —
posts, likes, reposts, follows — described in two passes:

1. **What Jetstream sends.** The wire format, in full. The menu of everything available.
2. **What we store.** The subset that reaches Parquet, and why the rest does not.

Keeping these apart matters because they diverge deliberately. Most of what arrives is
dropped, and the useful content of this doc is the gap between the two sections.

# What Jetstream Sends

## The Envelope

Every event has the same outer shape. The type-specific payload sits in `commit.record`.

```json
{
  "did": "did:plc:eygmaihciaxprqvxrfvl6flk",
  "time_us": 1784533137411372,
  "kind": "commit",
  "commit": {
    "rev": "3l3qo2vutsw2b",
    "operation": "create",
    "collection": "app.bsky.feed.post",
    "rkey": "3l3qo2vuowo2b",
    "cid": "bafyreidc6sykmtx7dbepnvdyzsjmyzpqfsn3fzo7lgvxfwbfjhqtwrxnfu",
    "record": { "…": "differs per collection" }
  }
}
```

| Field | Meaning |
|---|---|
| `did` | The actor — post author, liker, reposter, follower. |
| `time_us` | Unix microseconds, stamped by the Jetstream broker on receipt. Doubles as the replay cursor. |
| `kind` | `commit`, `identity`, or `account`. We keep only commits. |
| `commit.rev` | Repo revision. Orders multiple writes to the same record. |
| `commit.operation` | `create`, `update`, or `delete`. |
| `commit.collection` | Full NSID, e.g. `app.bsky.feed.post`. |
| `commit.rkey` | Record key within the actor's repo. |
| `commit.cid` | Content hash of this version of the record. |
| `commit.record` | The lexicon payload. Shapes below. |

The AT-URI is **not** on the wire. Jetstream sends `did`, `collection`, and `rkey`
separately; `at://{did}/{collection}/{rkey}` is reassembled by us.

Two clocks arrive, and they are not equally trustworthy. `time_us` is the broker's own.
`record.createdAt` is client-supplied — clients have wrong clocks, some backdate
deliberately, and some send outright junk.

## Post Records

`app.bsky.feed.post`

```json
{
  "$type": "app.bsky.feed.post",
  "createdAt": "2026-07-23T06:48:11.102Z",
  "text": "hello world",
  "langs": ["en"],
  "reply": {
    "root":   { "uri": "at://did:plc:abc/app.bsky.feed.post/3l3qroot", "cid": "bafyrootcid" },
    "parent": { "uri": "at://did:plc:def/app.bsky.feed.post/3l3rparent", "cid": "bafyparentcid" }
  },
  "embed": {
    "$type": "app.bsky.embed.images",
    "images": [{ "alt": "a cat", "image": { "…": "blob ref" } }]
  }
}
```

`reply` is absent on top-level posts. `embed` is absent on posts without media, and its
`$type` varies — images, external links, quoted records, or record-with-media. The lexicon
also permits optional `facets` (rich-text ranges for mentions and links), `tags`, and
`labels`.

## Like and Repost Records

`app.bsky.feed.like` and `app.bsky.feed.repost`

Identical record shapes — a `createdAt` plus a strongref to the post being acted on.

```json
{
  "$type": "app.bsky.feed.like",
  "createdAt": "2026-07-23T06:48:11.102Z",
  "subject": {
    "uri": "at://did:plc:abc/app.bsky.feed.post/3l3qtarget",
    "cid": "bafyreitargetcid"
  }
}
```

## Follow Records

`app.bsky.graph.follow`

`subject` here is a bare DID string, not a strongref object like likes and reposts use.

```json
{
  "$type": "app.bsky.graph.follow",
  "createdAt": "2026-07-23T06:48:11.102Z",
  "subject": "did:plc:eygmaihciaxprqvxrfvl6flk"
}
```

# What We Store

Four tables, one per data type, per the design doc's one-table-per-data-type rule. Every
column is nullable: one odd record must not fail an entire flush.

## Common Columns

Present in all four tables. Each table adds its own columns on top of these.

| Column | Parquet type | Source | Notes |
|---|---|---|---|
| `uri` | `string` | `at://{did}/{collection}/{rkey}` | Natural key, and the dedup key. Reassembled — not on the wire. |
| `did` | `string` | `did` | The actor. Redundant with `uri` and kept anyway — see below. |
| `cid` | `string` | `commit.cid` | Content hash. What `subject_cid` on likes/reposts points at. |
| `rev` | `string` | `commit.rev` | Orders writes to one `uri`. Nothing to order today, since only creates are ingested — captured now because Jetstream's retention window makes it unbackfillable later. |
| `created_at` | `timestamp[us, tz=UTC]` | `record.createdAt` | Client-supplied. Iceberg partition source, `day()` granularity. |
| `ingested_at` | `timestamp[us, tz=UTC]` | `time_us` | Broker clock, so the trustworthy end of `ingested_at - created_at` ingest lag. Microseconds are held exactly. |
| `run_id` | `string` | Generated at process start | Identifies the ingestion process that wrote the row. Not on the wire, and not produced by the parsers — the writer stamps it. |

`did` is derivable from `uri`, and is stored anyway for three reasons: it is the join and
group key for nearly every query; deriving it means a string split on every row of every
scan, which no engine can push down; and any future clustering strategy — a `bucket(N, did)`
partition transform, or a sort order — can only be expressed over a real column.

Note that this is *not* an argument about min/max pruning. Events arrive interleaved from
the whole firehose, so within any row group the DID range spans nearly the entire DID
space and prunes nothing. Min/max pruning belongs to the timestamps, which are clustered
by arrival.

**`run_id` is a column, not a filename, because filenames do not survive.** Iceberg names
its own data files (`00000-0-<uuid>.parquet`), so per-run traceability cannot be encoded in
the path. Compaction then makes the question permanently unanswerable from the layout: a
`BIN_PACK` rewrite merges files by size with no regard for content, so one post-compaction
file spans many runs. As a column it survives that rewrite, Iceberg keeps min/max stats for
it per file, and `table.inspect.files()` gives the file↔run mapping directly.

It is stamped by the writer rather than the parsers. The value is fixed for the life of a
process, so passing it down through every parser signature would be churn for something
that cannot vary per row. The consequence worth knowing is that the buffer's byte
accounting does not see it — `row_bytes` measures parser output, which is already
documented as a proxy rather than a measurement.

**Partitioning on `created_at` depends on clamping it.** A client-supplied timestamp is
unbounded, so a single junk `"0001-01-01"` permanently mints a year-0001 partition, and
honest backdating scatters tiny files across old partitions that never seal. The mitigation
is to repair implausible values — before Bluesky existed, or ahead of `ingested_at` — to
the broker clock. A repaired row is then identifiable by `created_at == ingested_at`, so no
separate fallback flag is needed. Iceberg's partition evolution means the `day()`
granularity can change later without rewriting history.

**`ingested_at` means the broker clock only on this path.** The backfill app reads whole
repos through `getRepo()`, which carries no per-record receive time, so a backfilled row can
only be stamped with `datetime.now()` at fetch. The two writers also overlap by
construction — backfilling an account re-fetches posts the live stream already captured —
producing two rows per `uri` that differ in `ingested_at` and are otherwise
indistinguishable. A `source` column (`jetstream` | `backfill`) is what makes that
resolvable, and should land before backfill writes to these tables.

## Posts Table

`app.bsky.feed.post`

| Column | Parquet type | Source | Notes |
|---|---|---|---|
| `text` | `string` | `record.text` | |
| `langs` | `list<string>` | `record.langs` | Nullable. Self-declared by the client. |
| `reply_root_uri` | `string` (nullable) | `record.reply.root.uri` | Null ⇒ top-level post. |
| `reply_parent_uri` | `string` (nullable) | `record.reply.parent.uri` | Null ⇒ top-level post. |
| `embed_type` | `string` (nullable) | `record.embed.$type` | Discriminator only, not the payload. |

```json
{
  "uri": "at://did:plc:eygmaihciaxprqvxrfvl6flk/app.bsky.feed.post/3l3qo2vuowo2b",
  "did": "did:plc:eygmaihciaxprqvxrfvl6flk",
  "cid": "bafyreidc6sykmtx7dbepnvdyzsjmyzpqfsn3fzo7lgvxfwbfjhqtwrxnfu",
  "rev": "3l3qo2vutsw2b",
  "created_at": "2026-07-23T06:48:11.102Z",
  "ingested_at": "2026-07-20T07:38:57.411372Z",
  "text": "hello world",
  "langs": ["en"],
  "reply_root_uri": "at://did:plc:abc/app.bsky.feed.post/3l3qroot",
  "reply_parent_uri": "at://did:plc:def/app.bsky.feed.post/3l3rparent",
  "embed_type": "app.bsky.embed.images"
}
```

## Likes and Reposts Tables

`app.bsky.feed.like` and `app.bsky.feed.repost`

Identical record shapes, so identical columns — but separate tables.

| Column | Parquet type | Source | Notes |
|---|---|---|---|
| `subject_uri` | `string` | `record.subject.uri` | The post being liked/reposted. Join key back to posts. |
| `subject_cid` | `string` (nullable) | `record.subject.cid` | Pins which version of the post was acted on. |

```json
{
  "uri": "at://did:plc:liker/app.bsky.feed.like/3l3qlikekey",
  "did": "did:plc:liker",
  "cid": "bafyreilikecid",
  "rev": "3l3qlikerev",
  "created_at": "2026-07-23T06:48:11.102Z",
  "ingested_at": "2026-07-20T07:38:57.411372Z",
  "subject_uri": "at://did:plc:abc/app.bsky.feed.post/3l3qtarget",
  "subject_cid": "bafyreitargetcid"
}
```

`did` is the actor (who liked); `subject_uri` is the target (what was liked).

## Follows Table

`app.bsky.graph.follow`

| Column | Parquet type | Source | Notes |
|---|---|---|---|
| `subject_did` | `string` | `record.subject` | The account being followed. |

```json
{
  "uri": "at://did:plc:follower/app.bsky.graph.follow/3l3qfollowkey",
  "did": "did:plc:follower",
  "cid": "bafyreifollowcid",
  "rev": "3l3qfollowrev",
  "created_at": "2026-07-23T06:48:11.102Z",
  "ingested_at": "2026-07-20T07:38:57.411372Z",
  "subject_did": "did:plc:eygmaihciaxprqvxrfvl6flk"
}
```

The edge `(did → subject_did)` is the follow graph. Both are DIDs, never handles.

# What We Drop, and Why

The rule is **denormalize what you filter and join on; derive what you only read**.
Derivability alone is not a reason to drop a column — `did` is derivable from `uri` and is
kept, because queries can filter on it.

| Dropped | Why |
|---|---|
| `commit.collection` | Constant within a table — the posts table only ever holds `app.bsky.feed.post`. Zero information per row. |
| `commit.rkey` | The last segment of `uri`. Nothing joins on it; the full URI is the identity. |
| `commit.operation` | Constant (`create`) today, because `process_commit_event` filters to creates. Add it in the same change that stops filtering. |
| `text_length` | Not on the wire — it would be `len(text)`. Cheap at query time, and storing it bakes in an ambiguity: Python counts code points, SQL `length()` varies by engine, and Bluesky's own 300-char cap counts graphemes. Three numbers for one post. |
| `kind` | Always `commit` in stored rows; identity and account events are filtered upstream. |
| `record.reply.*.cid` | The reply URIs are kept. The CIDs pin a version of the parent we have no use for. |
| `record.embed` payload | Only the `$type` discriminator is kept. Blob refs are not resolvable from Parquet. |
| `record.facets`, `tags`, `labels` | Not needed by any planned query. Revisit if rich-text or moderation analysis lands. |

`rev` and `operation` sit on opposite sides of the same judgment, and the distinction is
worth stating. `rev` varies per row today and cannot be recovered once the retention window
passes, so it is captured now. `operation` is genuinely one constant value, and becomes
recoverable the moment the ingest filter changes, so it waits.

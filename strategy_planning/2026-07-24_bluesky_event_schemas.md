<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [Purpose](#purpose)
- [Common Header (All Four Tables)](#common-header-all-four-tables)
- [Posts](#posts)
- [Likes and Reposts](#likes-and-reposts)
- [Follows](#follows)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# Purpose

Column definitions for the four Bluesky tables in
`docs/design_docs/2026-07-13_bluesky_ingestion_jetstream.md`: posts, likes, reposts, follows.

Each event arrives inside a Jetstream envelope, with the type-specific payload in
`commit.record`:

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

# Common Header (All Four Tables)

| Column | Parquet type | Source | Notes |
|---|---|---|---|
| `uri` | `string` | `at://{did}/{collection}/{rkey}` | Natural key. Reconstructed — Jetstream sends the parts, not the AT-URI. |
| `did` | `string` | `did` | The actor: post author, liker, reposter, follower. |
| `collection` | `string` | `commit.collection` | Full NSID. |
| `rkey` | `string` | `commit.rkey` | Record key within the repo. |
| `cid` | `string` | `commit.cid` | Content hash of this version of the record. |
| `rev` | `string` | `commit.rev` | Repo revision — orders writes to the same `uri`. |
| `operation` | `string` | `commit.operation` | `create` only for now. |
| `created_at` | `timestamp[us, tz=UTC]` | `record.createdAt` | Client-supplied. Iceberg partition source. |
| `ingested_at` | `timestamp[us, tz=UTC]` | `time_us` | Broker clock. |
| `time_us` | `int64` | `time_us` | Raw cursor value, for resumption. |

# Posts

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

| Column | Parquet type | Source | Notes |
|---|---|---|---|
| `text` | `string` | `record.text` | |
| `text_length` | `int32` | `len(text)` | Character count, not bytes. |
| `langs` | `list<string>` | `record.langs` | Nullable. Self-declared by the client. |
| `reply_root_uri` | `string` (nullable) | `record.reply.root.uri` | Null ⇒ top-level post. |
| `reply_parent_uri` | `string` (nullable) | `record.reply.parent.uri` | Null ⇒ top-level post. |
| `embed_type` | `string` (nullable) | `record.embed.$type` | Discriminator only, not the payload. |

Resulting row:

```json
{
  "uri": "at://did:plc:eygmaihciaxprqvxrfvl6flk/app.bsky.feed.post/3l3qo2vuowo2b",
  "did": "did:plc:eygmaihciaxprqvxrfvl6flk",
  "collection": "app.bsky.feed.post",
  "rkey": "3l3qo2vuowo2b",
  "cid": "bafyreidc6sykmtx7dbepnvdyzsjmyzpqfsn3fzo7lgvxfwbfjhqtwrxnfu",
  "rev": "3l3qo2vutsw2b",
  "operation": "create",
  "created_at": "2026-07-23T06:48:11.102Z",
  "ingested_at": "2026-07-23T06:48:11.411Z",
  "time_us": 1784533137411372,
  "text": "hello world",
  "text_length": 11,
  "langs": ["en"],
  "reply_root_uri": "at://did:plc:abc/app.bsky.feed.post/3l3qroot",
  "reply_parent_uri": "at://did:plc:def/app.bsky.feed.post/3l3rparent",
  "embed_type": "app.bsky.embed.images"
}
```

# Likes and Reposts

`app.bsky.feed.like` and `app.bsky.feed.repost`

Identical record shapes — a `createdAt` plus a strongref to the post being acted on — so
identical columns, but separate tables per the design doc's one-table-per-data-type rule.

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

| Column | Parquet type | Source | Notes |
|---|---|---|---|
| `subject_uri` | `string` | `record.subject.uri` | The post being liked/reposted. Join key back to posts. |
| `subject_cid` | `string` (nullable) | `record.subject.cid` | Pins which version of the post was acted on. |

Resulting row (like):

```json
{
  "uri": "at://did:plc:liker/app.bsky.feed.like/3l3qlikekey",
  "did": "did:plc:liker",
  "collection": "app.bsky.feed.like",
  "rkey": "3l3qlikekey",
  "cid": "bafyreilikecid",
  "rev": "3l3qlikerev",
  "operation": "create",
  "created_at": "2026-07-23T06:48:11.102Z",
  "ingested_at": "2026-07-23T06:48:11.411Z",
  "time_us": 1784533137411372,
  "subject_uri": "at://did:plc:abc/app.bsky.feed.post/3l3qtarget",
  "subject_cid": "bafyreitargetcid"
}
```

`did` is the actor (who liked); `subject_uri` is the target (what was liked).

# Follows

`app.bsky.graph.follow`

`subject` here is a bare DID string, not a strongref object like likes and reposts use.

```json
{
  "$type": "app.bsky.graph.follow",
  "createdAt": "2026-07-23T06:48:11.102Z",
  "subject": "did:plc:eygmaihciaxprqvxrfvl6flk"
}
```

| Column | Parquet type | Source | Notes |
|---|---|---|---|
| `subject_did` | `string` | `record.subject` | The account being followed. |

Resulting row:

```json
{
  "uri": "at://did:plc:follower/app.bsky.graph.follow/3l3qfollowkey",
  "did": "did:plc:follower",
  "collection": "app.bsky.graph.follow",
  "rkey": "3l3qfollowkey",
  "cid": "bafyreifollowcid",
  "rev": "3l3qfollowrev",
  "operation": "create",
  "created_at": "2026-07-23T06:48:11.102Z",
  "ingested_at": "2026-07-23T06:48:11.411Z",
  "time_us": 1784533137411372,
  "subject_did": "did:plc:eygmaihciaxprqvxrfvl6flk"
}
```

The edge `(did → subject_did)` is the follow graph. Both are DIDs, never handles.

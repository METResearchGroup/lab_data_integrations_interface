<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [Purpose](#purpose)
- [Common Columns](#common-columns)
- [Posts](#posts)
- [Likes and Reposts](#likes-and-reposts)
- [Follows](#follows)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# Purpose

What we store in each of the four Bluesky tables from
`docs/design_docs/2026-07-13_bluesky_ingestion_jetstream.md`: posts, likes, reposts, follows.

Source paths below refer to the Jetstream envelope:

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

# Common Columns

Present in all four tables.

| Column | Parquet type | Source | Notes |
|---|---|---|---|
| `uri` | `string` | `at://{did}/{collection}/{rkey}` | Natural key. Reconstructed — Jetstream sends the parts, not the AT-URI. |
| `did` | `string` | `did` | The actor: post author, liker, reposter, follower. |
| `cid` | `string` | `commit.cid` | Content hash. What `subject_cid` on likes/reposts points at. |
| `created_at` | `timestamp[us, tz=UTC]` | `record.createdAt` | Client-supplied. Iceberg partition source. |
| `ingested_at` | `timestamp[us, tz=UTC]` | `time_us` | Broker clock, the only server-side timestamp. If a skewed `created_at` is repaired to broker time, the two are equal — so no separate fallback flag is needed. |

# Posts

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
  "created_at": "2026-07-23T06:48:11.102Z",
  "ingested_at": "2026-07-23T06:48:11.411Z",
  "text": "hello world",
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

| Column | Parquet type | Source | Notes |
|---|---|---|---|
| `subject_uri` | `string` | `record.subject.uri` | The post being liked/reposted. Join key back to posts. |
| `subject_cid` | `string` (nullable) | `record.subject.cid` | Pins which version of the post was acted on. |

```json
{
  "uri": "at://did:plc:liker/app.bsky.feed.like/3l3qlikekey",
  "did": "did:plc:liker",
  "cid": "bafyreilikecid",
  "created_at": "2026-07-23T06:48:11.102Z",
  "ingested_at": "2026-07-23T06:48:11.411Z",
  "subject_uri": "at://did:plc:abc/app.bsky.feed.post/3l3qtarget",
  "subject_cid": "bafyreitargetcid"
}
```

`did` is the actor (who liked); `subject_uri` is the target (what was liked).

# Follows

`app.bsky.graph.follow`

`subject` here is a bare DID string, not a strongref object like likes and reposts use.

| Column | Parquet type | Source | Notes |
|---|---|---|---|
| `subject_did` | `string` | `record.subject` | The account being followed. |

```json
{
  "uri": "at://did:plc:follower/app.bsky.graph.follow/3l3qfollowkey",
  "did": "did:plc:follower",
  "cid": "bafyreifollowcid",
  "created_at": "2026-07-23T06:48:11.102Z",
  "ingested_at": "2026-07-23T06:48:11.411Z",
  "subject_did": "did:plc:eygmaihciaxprqvxrfvl6flk"
}
```

The edge `(did → subject_did)` is the follow graph. Both are DIDs, never handles.

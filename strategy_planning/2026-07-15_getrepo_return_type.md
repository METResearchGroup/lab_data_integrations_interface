<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [`com.atproto.sync.getRepo` return type](#comatprotosyncgetrepo-return-type)
  - [What you get back](#what-you-get-back)
  - [1. Commit block](#1-commit-block)
  - [2. MST tree-node block](#2-mst-tree-node-block)
  - [3. Record blocks (per collection)](#3-record-blocks-per-collection)
    - [`app.bsky.feed.post`](#appbskyfeedpost)
    - [`app.bsky.feed.like`](#appbskyfeedlike)
    - [`app.bsky.feed.repost`](#appbskyfeedrepost)
    - [`app.bsky.graph.follow`](#appbskygraphfollow)
  - [Mapping to our CSV columns](#mapping-to-our-csv-columns)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# `com.atproto.sync.getRepo` return type

What the endpoint actually returns, block by block, and which fields are always present vs.
optional. Verified against the real lexicon/schema definitions in `bluesky-social/atproto`
(`lexicons/app/bsky/feed/*.json`, `lexicons/app/bsky/graph/follow.json`, and
`packages/repo/src/types.ts` / `packages/repo/src/mst/mst.ts`) rather than written from memory.

Context: this is the "Part B" of the AOC-followers backfill plan — call `getRepo(did)` for each
of our 10 target users, decode the response, walk the tree to recover each record's URI, and map
the fields below into `posts.csv` / `likes.csv` / `reposts.csv` / `follows.csv`.

## What you get back

One HTTP response: raw bytes in CAR format (`Content-Type: application/vnd.ipld.car`). Decoding
that (e.g. via `atproto`'s `CAR.from_bytes()`) gives you `root` (a CID) plus `blocks`, a flat
`dict[CID, decoded_block]`. `blocks` mixes together three structurally different kinds of block
with nothing to distinguish them except their own shape:

1. **One commit block** — reachable via `root`
2. **Many MST tree-node blocks** — the index structure
3. **Many record/value blocks** — the actual posts/likes/reposts/follows content

## 1. Commit block

Reached by decoding the block at `root`. This is the repo's signed "head" — everything else hangs
off `data`.

| field | type | required? | notes |
|---|---|---|---|
| `did` | string | **always present** | whose repo this is |
| `version` | literal `3` | **always present** | `2` for legacy repos (rare) — see note below |
| `data` | CID | **always present** | pointer to the MST root node |
| `rev` | string | **always present** (v3) | revision marker, used for incremental `since=` syncs |
| `prev` | CID or `null` | **key always present, value may be `null`** | kept for v2 backwards-compat; don't rely on it for anything |
| `sig` | bytes | **always present** | signature over the rest of the commit |

Note: a small number of older repos may still be in the legacy v2 commit format, where `rev` is
actually optional. Current repos are v3 and always have all six fields above as keys — the only
one whose *value* can be empty (`null`) is `prev`.

## 2. MST tree-node block

Pure index structure — no record content lives here, only compressed keys and pointers.

| field | type | required? | notes |
|---|---|---|---|
| `l` | CID or `null` | **key always present, value may be `null`** | pointer to the left-most subtree (keys before the first entry); `null` if there is none |
| `e` | array of entries | **always present** | may be an empty array |

Each entry inside `e`:

| field | type | required? | notes |
|---|---|---|---|
| `p` | number | **always present** | length of the prefix this entry's key shares with the *previous* key in this node |
| `k` | bytes | **always present** | the rest of the key, after the shared prefix |
| `v` | CID | **always present** | pointer to the value block (the actual record) |
| `t` | CID or `null` | **key always present, value may be `null`** | pointer to the subtree between this entry and the next one |

Reconstructing a full key means walking entries in order, diving into subtrees whenever `l`/`t`
point somewhere, and accumulating `previous_key[:p] + k` at each leaf. The final key
(`{collection}/{rkey}`) plus the DID from the commit block is the record's URI:
`at://{did}/{collection}/{rkey}`.

## 3. Record blocks (per collection)

Every record has a `$type` field identifying its collection (not a declared lexicon "property,"
but always present in practice — it's how you tell record blocks apart from everything else in
`blocks` if you're not walking the tree).

### `app.bsky.feed.post`

| field | required? | notes |
|---|---|---|
| `text` | **required** | may be an empty string if the post is embed-only |
| `createdAt` | **required** | |
| `facets` | optional | mentions/links/hashtags as byte-range annotations on `text` |
| `reply` | optional | `{root: strongRef, parent: strongRef}` — present only for threaded replies |
| `embed` | optional | union of `images` / `video` / `gallery` / `external` / `record` (quote post) / `recordWithMedia` |
| `langs` | optional | up to 3 language codes |
| `labels` | optional | self-applied content-warning labels |
| `tags` | optional | up to 8 additional hashtags not in the text/facets |
| `entities` | optional, **deprecated** | superseded by `facets`; safe to ignore |

### `app.bsky.feed.like`

| field | required? | notes |
|---|---|---|
| `subject` | **required** | `strongRef` (`{uri, cid}`) — the post being liked |
| `createdAt` | **required** | |
| `via` | optional | `strongRef` to the record (usually a repost) through which the user encountered the content |

### `app.bsky.feed.repost`

Identical shape to `like`:

| field | required? | notes |
|---|---|---|
| `subject` | **required** | `strongRef` — the post being reposted |
| `createdAt` | **required** | |
| `via` | optional | same meaning as on `like` |

### `app.bsky.graph.follow`

| field | required? | notes |
|---|---|---|
| `subject` | **required** | plain DID string (not a `strongRef` — unlike like/repost) of the account being followed |
| `createdAt` | **required** | |
| `via` | optional | same meaning as on `like`/`repost` |

## Mapping to our CSV columns

- `author_handle` / `author_did` — not in any of the above; carried in from Phase A (discovery), not part of the record content.
- `uri` — not a field on any block; only obtainable by walking the MST as described in section 2.
- Everything else in `posts.csv` / `likes.csv` / `reposts.csv` / `follows.csv` maps directly to a field in section 3, with `null`/empty for any optional field not present on a given record.
- `via` is not currently in our schema for likes/reposts/follows — open decision from earlier discussion on whether to add it.

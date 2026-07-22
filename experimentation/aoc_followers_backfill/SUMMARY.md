# `getRepo`: design choices and future scaling

Summary of the decisions behind `experimentation/aoc_followers_backfill/`, and what would need to
change to run this against more than 10 users. Companion to
`strategy_planning/2026-07-15_getrepo_return_type.md`, which documents the exact field-level
schema this pipeline decodes.

## Why `getRepo` instead of the alternatives

Three options existed for pulling a user's historical activity:

- **Jetstream** — real-time firehose, but can't look back further than a few days. Ruled out
  immediately; this project needs a 4-week window.
- **`com.atproto.repo.listRecords`** — one paginated call per collection per user (4 calls minimum
  for posts/likes/reposts/follows, more with pagination). Server does all the parsing; you get
  clean JSON back.
- **`com.atproto.sync.getRepo`** — one call per user, full repo history as a binary CAR file.
  Client does the parsing.

We chose `getRepo`. Two reasons drove it:

1. **It's the only way to get "what did this user like."** There's no AppView endpoint for that
   (`getLikes` only returns who liked a *given* post, not what a *given user* liked) — the like
   *records* themselves, reachable via raw repo access, are the only source for that.
2. **One request per user**, not one per collection. At n=10 this barely matters, but it's the
   more natural fit for "pull everything, filter locally to a time window" than four separate
   paginated queries per user.

The tradeoff we accepted: `getRepo` has no server-side date filtering, so every call downloads a
user's *entire* history, and filtering to the last 4 weeks happens client-side, after decoding.
For a bounded set of users this is cheap; it stops being the efficient choice if the goal shifts
to "repeatedly pull only recent activity" for a large population (see Scaling below).

## Two different backend services, not one

The implementation talks to three distinct services, and mixing them up breaks things:

| service | used for | why |
|---|---|---|
| `bsky.social` (entryway/AppView), authenticated | discovery: `resolveHandle`, `getFollowers`, `getProfiles`, `getAuthorFeed` | These are indexed, cross-repo queries (follower counts, feeds) that only an AppView computes. The relay has no concept of these — confirmed empirically, it 404s on `app.bsky.*` calls entirely. |
| `bsky.network` (relay), unauthenticated | `getRepo` | The relay mirrors every repo on the network, so it can serve `getRepo` for *any* DID regardless of which PDS actually hosts them. It has no login endpoint at all — sync-only. |
| — (not used) | — | `bsky.social` does **not** proxy `getRepo` for arbitrary DIDs — confirmed empirically (`RepoNotFound` calling it for AOC's own account). Origin-PDS routing via the PLC directory would be the other way to reach a specific repo, but isn't needed while the relay covers everyone. |

`client.py` reflects this split directly: `create_client()` (entryway, authenticated) vs.
`create_relay_client()` (relay, no auth).

## Decoding `getRepo`'s response ourselves

`getRepo` returns a CAR file: a commit block, many Merkle Search Tree (MST) index-node blocks, and
many record-content blocks, all flattened into one `CID -> block` map. The `atproto` SDK's `CAR`
class only unpacks the CAR container (`CAR.from_bytes()` gives you that flat block map) — it does
not walk the MST for you. We wrote that ourselves (`mst.py`), because a record's own block has no
idea what its own path/URI is; that only exists as compressed key fragments spread across the tree
structure, reconstructed by walking it (see the strategy doc for the exact algorithm).

A few implementation specifics that took empirical checking to pin down (not documented anywhere
obvious, verified against real API responses rather than assumed):

- Nested CID references inside decoded blocks (an MST entry's `v`/`t`/`l`, or a commit's `data`)
  come back from `libipld` as raw `bytes`, decodable directly via `CID.decode(bytes)` — no
  multibase-prefix stripping needed.
- A `strongRef` (used by `like`/`repost`'s `subject`, and quote-post embeds) is a plain string
  `cid`, unlike the MST's internal pointers — different encoding for a similarly-named concept.
- `app.bsky.embed.recordWithMedia` nests the quoted post one level deeper
  (`embed.record.record.uri`) than plain `app.bsky.embed.record` (`embed.record.uri`).

Validation: decoded AOC's repo and got exactly 611 `app.bsky.feed.post` records, matching her
`postsCount` from the AppView exactly — strong confirmation the walk is correct, not just
"didn't crash."

## What "scale" actually costs right now

At n=10 users, this pipeline is about as cheap as it gets: 1 relay endpoint, 10 sequential
`getRepo` calls, no rate limiting encountered, no PLC directory lookups needed. That's a direct
consequence of hitting the relay (which already covers the whole network) instead of routing
per-user to origin PDS hosts.

## How this would need to change to scale up

The `bluesky-research` reference repo's `manager.py`/`worker.py` architecture (grouping DIDs by
origin PDS shard, running one rate-limited worker per shard, all async) exists to solve problems
that don't show up until volume is much higher. Concretely, scaling this pipeline up would mean:

1. **Reintroduce PLC-directory resolution and per-shard fan-out.** One relay endpoint is a single
   shared rate-limit bucket — fine for 10 requests, not for thousands. Past some volume, routing
   `getRepo` calls to each DID's actual origin PDS (resolved via the PLC directory, same as the
   reference repo's `query_plc_endpoint.py`) spreads load across many independently-rate-limited
   servers instead of queueing behind one.
2. **Go concurrent.** `backfill_user()` is currently called once per user, synchronously, in a
   plain `for` loop in `main.py`. That's fine for 10 sequential downloads; it would need to become
   async (or thread-pooled) to not be the bottleneck at higher user counts.
3. **Reconsider the "always fetch full history" cost.** Fine for a one-off pull of 10 accounts;
   wasteful if this becomes a recurring job against the same users. `getRepo` accepts a `since`
   (revision) parameter for incremental re-sync — worth using once an initial full pull's revision
   is checkpointed somewhere, so repeat runs only fetch what's changed instead of the full repo
   again.
4. **Move off flat CSV/JSON.** Fine for an experimentation-scale run; a recurring or larger job
   would fit better into `data_platform`'s existing ingestion conventions (Parquet, dataset
   registry, `metadata.json`-per-stage pattern already used elsewhere in this repo) rather than a
   single timestamped folder of CSVs.
5. **`discovery.py` is AOC/n=10-specific; `backfill.py` mostly isn't.** `backfill_user(user,
   relay_client)` already takes a generic `{handle, did}` and has no dependency on how that user
   was found — reusable as-is for a different or larger candidate list. `get_ten_users()` would
   need to be swapped out (or generalized) for a different discovery criteria or population size.

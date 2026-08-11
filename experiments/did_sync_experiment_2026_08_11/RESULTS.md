# DID sync discovery experiment — 2026-08-11

Run started (UTC): `2026-08-11T13:14:48.161967+00:00`

## Question

Which DID discovery strategy yields more *valid* accounts (by activity/graph thresholds) when sampling 1000 DIDs?

## Validity criteria

An account is **valid** if all of the following hold:

1. At least **10** followers (AppView `followersCount`)
2. At least **10** followees (`app.bsky.graph.follow` records via `getRepo`)
3. At least **20** original posts in the last ~6 months (`app.bsky.feed.post` without `reply`)
4. At least **20** interactions in the last ~6 months (like + save/bookmark + quote + repost + reply)

## Method

- **Ablation 1 (PLC):** `https://plc.directory/export` from genesis, unique DIDs.
- **Ablation 2 (AOC BFS):** `getFollowers` BFS starting at `aoc.bsky.social`.
- **Profile/activity:** `com.atproto.sync.getRepo` against `bsky.network` (same decode approach as `experimentation/aoc_followers_backfill`), plus AppView `getProfiles` for follower counts / handles / createdAt (follower edges are not present in a user's own repo).

## Results

| Ablation | DIDs | Valid DIDs | Validity rate | Discovery requests | Discovery runtime (s) | Discovery rate-limits | getRepo requests | getRepo rate-limits | getRepo errors |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ablation1_plc | 5 | 3 | 60.0% | 1 | 0.07 | 0 | 5 | 1 | 1 |
| ablation2_aoc_bfs | 5 | 1 | 20.0% | 2 | 0.43 | 0 | 5 | 0 | 0 |

## Comparison

**ablation1_plc** produced more valid DIDs (3 vs 1, 60.0% vs 20.0%).

### Discovery cost

- **ablation1_plc**: 1 requests, 0.07s, 0 rate-limit events.
  - PLC pages / final cursor: `1` / `2022-11-17T03:30:47.787Z`
  - No rate-limit related response headers observed.
- **ablation2_aoc_bfs**: 2 requests, 0.43s, 0 rate-limit events.
  - Seed: `aoc.bsky.social` (did:plc:p7gxyfr5vii5ntpwo7f6dhe2), followers≈2209741
  - Max BFS depth reached: `1`, pages by depth: `{0: 1}`

### Interpretation

- PLC genesis export preferentially samples the earliest registered DIDs (often highly active Bluesky staff/early adopters, but also includes dormant invite-era accounts and some very large repos).
- AOC follower BFS preferentially samples accounts that follow a high-engagement political account (and, at deeper levels, followers of those followers), which may skew toward currently active users.
- Validity requires recent original posting *and* interactions, so discovery methods that surface currently engaged graph neighborhoods should outperform raw PLC chronology if early DIDs are mostly inactive.

## Artifacts

Per ablation under `data/<ablation>/`:

- `discovery.json` — DIDs, request/runtime/rate-limit metrics
- `profiles.jsonl` — per-DID follower/post/followee/created + activity
- `summary.json` — rollup counts used in this file


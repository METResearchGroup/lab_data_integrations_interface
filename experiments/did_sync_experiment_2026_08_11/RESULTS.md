# DID sync discovery experiment, 2026-08-11

Run started (UTC): `2026-08-11T14:38:19.403852+00:00`

## Question

Which DID discovery strategy yields more valid accounts under shared activity and graph thresholds when sampling the same number of DIDs?

## Validity criteria

An account is valid when all of the following hold:

1. At least 10 followers (AppView `followersCount`)
2. At least 10 followees (`app.bsky.graph.follow` via `getRepo`)
3. At least 20 original posts in the last ~6 months
4. At least 20 interactions in the last ~6 months (like + bookmark/save + quote + repost + reply)

## Method

- Ablation 1 (PLC): `https://plc.directory/export` from a recent cursor, unique DIDs.
- Ablation 2 (AOC BFS): `getFollowers` breadth first search starting at `aoc.bsky.social`.
- Profile and activity: `com.atproto.sync.getRepo` against `bsky.network` (decode helpers from `experimentation/aoc_followers_backfill`), plus AppView `getProfiles` for follower counts and handles.

## Results

| Ablation | DIDs | Valid DIDs | Validity rate | Discovery requests | Discovery runtime (s) | Discovery rate-limits | getRepo requests | getRepo rate-limits | getRepo errors |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ablation1_plc | 1000 | 1 | 0.1% | 2 | 0.16 | 0 | 1000 | 191 | 899 |
| ablation2_aoc_bfs | 1000 | 183 | 18.3% | 13 | 1.86 | 0 | 1000 | 0 | 2 |

## Comparison

ablation2_aoc_bfs produced more valid DIDs (183 vs 1, delta 182; 18.3% vs 0.1%).

### Discovery cost

- ablation1_plc: 2 requests, 0.16s, 0 rate-limit events.
  - `initial_after`: `2026-08-10T14:06:26.286Z`
  - `final_after`: `2026-08-10T14:13:26.640Z`
  - `pages`: `2`
  - `lookback_hours_final`: `24`
  - `rate_limit_header_sample`: `{}`
- ablation2_aoc_bfs: 13 requests, 1.86s, 0 rate-limit events.
  - `seed_handle`: `aoc.bsky.social`
  - `seed_did`: `did:plc:p7gxyfr5vii5ntpwo7f6dhe2`
  - `seed_followers_count`: `2209744`
  - `max_depth_reached`: `0`
  - `pages_by_depth`: `{'0': 12}`

### Interpretation

PLC recent-cursor export samples accounts that registered or updated identity operations near the lookback window, which may mix active new accounts with dormant ones.

AOC follower breadth first search samples accounts connected to a high engagement political neighborhood, which may skew toward currently active users.

Validity requires recent original posting and interactions, so the method that surfaces currently engaged graph neighborhoods should outperform recent PLC chronology when newly registered DIDs are inactive or when getRepo fails often for that sample. These numbers inform backfill seed choice. They do not by themselves prove production readiness.

## Artifacts

Per ablation under `data/<ablation>/`:

- `discovery.json`: DIDs, request/runtime/rate-limit metrics
- `profiles.jsonl`: per-DID follower/post/followee/created + activity
- `summary.json`: rollup counts used in this file

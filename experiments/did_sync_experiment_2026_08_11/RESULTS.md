# DID sync discovery experiment, 2026-08-11

Run started (UTC): `2026-08-11T15:45:42.426135+00:00`

## Question

Which DID discovery strategy yields more valid accounts under shared activity and graph thresholds when sampling the same number of DIDs?

## Validity criteria

An account is valid when all of the following hold:

1. At least 10 followers (AppView `followersCount`)
2. At least 10 followees (`app.bsky.graph.follow` via `getRepo`)
3. At least 20 original posts in the last ~6 months
4. At least 20 interactions in the last ~6 months (like + bookmark/save + quote + repost + reply)

## Method

- Ablation 1 (PLC recent): `https://plc.directory/export` from a recent cursor (~24h lookback), unique DIDs.
- Ablation 2 (AOC BFS): `getFollowers` breadth first search starting at `aoc.bsky.social`.
- Ablation 3 (PLC older): `https://plc.directory/export` from a fixed ~6 month old cursor, walking forward for unique DIDs.
- Profile and activity: `com.atproto.sync.getRepo` starting at `bsky.network` with PDS redirect following via httpx (decode helpers from `experimentation/aoc_followers_backfill`), plus AppView `getProfiles` for follower counts and handles.

## Results

| Ablation | DIDs | Valid DIDs | Validity rate | Discovery requests | Discovery runtime (s) | Discovery rate-limits | getRepo requests | getRepo rate-limits | getRepo errors |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ablation1_plc | 1000 | 1 | 0.1% | 1 | 0.07 | 0 | 1000 | 0 | 906 |
| ablation2_aoc_bfs | 1000 | 183 | 18.3% | 13 | 2.25 | 0 | 1000 | 0 | 0 |
| ablation3_plc_old | 1000 | 1 | 0.1% | 2 | 0.16 | 0 | 1000 | 0 | 828 |

## Comparison

ablation2_aoc_bfs produced the most valid DIDs (183 vs next 1, delta 182; ranking by valid count: ablation2_aoc_bfs=183, ablation1_plc=1, ablation3_plc_old=1).

### Discovery cost

- ablation1_plc: 1 requests, 0.07s, 0 rate-limit events.
  - `initial_after`: `2026-08-10T15:45:42.426Z`
  - `final_after`: `2026-08-10T15:51:57.097Z`
  - `pages`: `1`
  - `lookback_hours_final`: `24`
  - `rate_limit_header_sample`: `{}`
- ablation2_aoc_bfs: 13 requests, 2.25s, 0 rate-limit events.
  - `seed_handle`: `aoc.bsky.social`
  - `seed_did`: `did:plc:p7gxyfr5vii5ntpwo7f6dhe2`
  - `seed_followers_count`: `2209746`
  - `max_depth_reached`: `0`
  - `pages_by_depth`: `{'0': 12}`
- ablation3_plc_old: 2 requests, 0.16s, 0 rate-limit events.
  - `initial_after`: `2026-02-10T13:11:34.579Z`
  - `final_after`: `2026-02-10T13:22:14.880Z`
  - `pages`: `2`
  - `lookback_hours_final`: `4392`
  - `lookback_hours_initial`: `4392`
  - `expand_lookback`: `False`
  - `rate_limit_header_sample`: `{}`

### Interpretation

PLC recent-cursor export samples accounts that registered or updated identity operations near the lookback window, which may mix active new accounts with dormant ones.

PLC older-cursor export samples identity operations from about six months earlier. Those accounts have had longer to accumulate followers and activity, but may still include takedowns, deactivated repos, or unreachable PDS hosts.

AOC follower breadth first search samples accounts connected to a high engagement political neighborhood, which may skew toward currently active users.

Validity requires recent original posting and interactions, so the method that surfaces currently engaged graph neighborhoods should outperform recent PLC chronology when newly registered DIDs are inactive or when getRepo fails often for that sample. getRepo calls run sequentially with spacing, follow relay-to-PDS redirects, and retry only true 429/transient failures. Remaining errors are account or host failures (for example RepoNotFound, RepoTakendown, or an unreachable redirected PDS such as DNS failures), not quota noise. These numbers inform backfill seed choice. They do not by themselves prove production readiness.

### getRepo error breakdown

- ablation1_plc: pds_unreachable=666, repo_deactivated=1, repo_not_found=229, repo_takendown=10 (DIDs that hit a 429 at least once during retries: 0)
- ablation2_aoc_bfs: none (DIDs that hit a 429 at least once during retries: 0)
- ablation3_plc_old: other=1, pds_unreachable=585, repo_deactivated=4, repo_not_found=16, repo_takendown=222 (DIDs that hit a 429 at least once during retries: 0)

## Artifacts

Per ablation under `data/<ablation>/`:

- `discovery.json`: DIDs, request/runtime/rate-limit metrics
- `profiles.jsonl`: per-DID follower/post/followee/created + activity
- `summary.json`: rollup counts used in this file

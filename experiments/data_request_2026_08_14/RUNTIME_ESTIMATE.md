# Runtime estimate

Pulling the files in `EXPECTED_FILES.md` for 8,431 DIDs will take hours if you stop after getRepo, and about 1 to 4 days if you also look up posts with `getPosts`. The request window is 12 months. The activity rates below come from a 6-month measurement (about 183 days), so unique post lookups for 12 months can be up to about twice as many if posting and liking stay steady.

Login is not required. You will spend most of the time looking up referenced posts with `getPosts`.

## Estimated wall clock

| Scope | Optimistic | Likely | Pessimistic |
|---|---|---|---|
| getRepo + getProfiles only (no `posts.csv` lookup) | about 2 hours | about 3 to 6 hours | about 10 hours |
| Full `EXPECTED_FILES.md` (look up unique post URIs) | about 1 day | about 1 to 2 days | about 3 to 4 days |

Relative to the 6-month measurement, a 12-month window sits toward the high end of the table.

## Auth vs public

Sources: [lab_wiki, what data is available](https://github.com/METResearchGroup/lab_wiki/blob/main/docs/manuals/tools/bluesky/WHAT_DATA_IS_AVAILABLE_IN_BLUESKY.md) and [Bluesky rate limits](https://docs.bsky.app/docs/advanced-guides/rate-limits).

| Call | Auth? | Role in the extract | Time |
|---|---|---|---|
| `getRepo` via `bsky.network` | No | Posts, likes, reposts, follows, profile record | Most of the time if you skip post lookup |
| `getProfiles` on public AppView | No | Handle, bio, follower and followee counts | Minutes (about 338 batches of 25) |
| `getPosts` on public AppView | No (max 25 URIs) | Text, media, langs, author, engagement counts on `posts.csv` | Most of the time if you fill `posts.csv` |
| `getActorLikes` | Yes. Do not use it. | Replaced by like records in getRepo | n/a |
| Bookmarks / saves | Private | Empty `saves.csv` | None |

`getPosts` and `getProfiles` do not need a session. `public.api.bsky.app` is the cached public AppView. Relay `getRepo` has no login.

The 3,000 requests per 5 minutes (about 10 per second) figure is not an AppView limit. It is the Bluesky-hosted PDS overall API cap, measured per IP, for authenticated traffic that goes through the account's PDS (`bsky.social` / entryway). Official wording is on [Rate Limits, Hosted Account (PDS) Limits](https://docs.bsky.app/docs/advanced-guides/rate-limits).

> Overall API Requests (all endpoints)

> - Rate limited by IP
> - 3000 per 5 minutes

Direct AppView hosts (`api.bsky.app`, `public.api.bsky.app`) "do not support authentication" and have "generous rate-limits" with a contact path if you hit them. Same page, [Bluesky API Limits](https://docs.bsky.app/docs/advanced-guides/rate-limits).

Bulk `getPosts` should use `public.api.bsky.app`, not a logged-in PDS session. A logged-in PDS session would inherit the 3,000 requests per 5 minutes IP cap.

Relay `getRepo` is a different service. The DID-sync experiment under `experiments/did_sync_experiment_2026_08_11/` paced relay calls at a 0.15 second minimum interval, and cited about 6,000 getRepo calls per 300 seconds (about 20 per second) as the advertised relay budget. The experiment saw 0 HTTP 429s in 4,000 getRepo calls.

## Measured getRepo (2026-08-11)

The DID-sync run in `experiments/did_sync_experiment_2026_08_11/` paced getRepo at a 0.15 second minimum interval, with 2 workers and HTTP serialized on one relay client.

| Run | DIDs | Wall | Per DID | 429s | Scale to 8,431 |
|---|---:|---|---:|---:|---|
| Ablation 2 (AOC followers) | 1,000 | 774 s (12.9 min) | 0.77 s | 0 | about 1.8 hours |
| Ablation 4 (listRepos, heavier repos) | 1,000 | 4,127 s (69 min) | 4.13 s | 0 | about 9.7 hours 
Accounts from the AOC follower sample are a closer match to greedy-10 than listRepos accounts. getRepo returns the full repo either way. A 12-month vs 6-month filter does not shrink the download.

## What `getPosts` is for

A like or repost record in getRepo is only `{ subject: { uri, cid }, createdAt }`. A quote or reply post in getRepo has the cohort member's text and pointers (`quoted_post_uri` / `parent_post_uri`), not the other post's body or counts.

Nick's per-post fields that are not stored on the PDS post record, and that AppView `getPosts` adds (`app.bsky.feed.defs#postView`):

- `likeCount`, `replyCount`, `repostCount`, `quoteCount`, `bookmarkCount` become `posts.csv` `like_count` through `save_count`
- Author handle and display name for posts the member did not write
- Embed data used to set `has_image` / `has_video` from AppView media, not blob refs
- `indexedAt`
- Full `record.text`, langs, and reply pointers for other people's posts (liked, reposted, quoted, replied-to)

The repo already contains text, langs, media blob refs, and timestamps for posts the member wrote. Member-authored rows can use `hydration_status=repo_only` if AppView is skipped. Engagement counts on member-authored posts still need `getPosts`, or the counts stay null. Every liked, reposted, quoted, or parent URI still needs `getPosts`, or `getRecord` on someone else's PDS.

`getPosts` batches up to 25 AT-URIs per request. The time cost is the number of those HTTP calls, not the size of each post. Each call is a small JSON lookup. We may still need hundreds of thousands to millions of calls.

getRepo for one person already has that person's own posts. It does not have the posts they liked. A like or repost is only a pointer. A quote or reply has their text plus a pointer at someone else's post. Filling `posts.csv` means looking up those other posts (and, if we want counts on member-authored posts, looking those up too).

Likes dominate the volume. Counts below come from `experiments/did_sync_experiment_2026_08_11/data/ablation2_aoc_bfs/profiles.jsonl`. The per-person upper bound is originals + likes + reposts + replies + quotes, before removing duplicate URIs.

| Who | Likes per person (6 months) | Events that need a post body or counts, per person |
|---|---:|---:|
| Mixed 1,000 followers (many lurkers) | mean about 950, median 10 | about 1,400 |
| Active subset (183 valid accounts) | mean about 4,100, median 777 | about 6,500 |

Greedy-10 people sit in overlapping seed pools, so they look more like the active group than random lurkers. One heavy account in that sample had about 65,000 likes in 6 months, which is about 2,600 `getPosts` calls for that person alone.

Scale to 8,431 people with no URI sharing (6-month proxy):

| Population proxy | URIs / person (upper bound) | × 8,431, before removing duplicate URIs | getPosts calls (25/req) |
|---|---:|---:|---:|
| AOC BFS all 1,000 | 1,418 | 12.0 M | 478 k |
| AOC BFS valid 183 | 6,524 | 55.0 M | 2.2 M |

At 10 `getPosts` calls per second (25 URIs each, so about 250 posts per second):

- 478 k calls take about 13 hours
- 2.2 M calls take about 61 hours (about 2.5 days)

That is why lookup, not getRepo, is the long pole. getRepo is one download per account (about 0.8 to 4 seconds each, a few hours for 8,431). `getPosts` is one batch per 25 referenced posts, and referenced posts can number in the millions.

Removing duplicate URIs helps only when many members like the same post. Related neighborhoods overlap some, but not enough to turn millions of likes into thousands of unique posts. A 2× to 10× cut still leaves a day-scale job. A 12-month window can approach about 2 times the URI counts in the table. HTTP 429 responses make the job take longer.

Ways to make it fast, matching `docs/plans/2026-08-14_data_request_nick_c4e812/plan.md`:

- `--profiles-only` writes handles, bios, and counts in minutes.
- `--hydrate none` after a resumable getRepo cache is the about 2 to 10 hour job. `posts.csv` keeps member text from getRepo (`repo_only`) and other URIs as `pending`.
- `--hydrate own_posts` looks up only posts the members wrote, to get counts, not every like target.
- `--hydrate quotes_replies` adds quoted posts and reply parents.
- `--hydrate all` is the 1 to 4 day like-target job. Deduplicate URIs, skip rows that are already `ok`, and call public AppView, not the PDS 3,000 per 5 minutes cap.

## Combined time

| Scope | Wall clock |
|---|---|
| getRepo + getProfiles only | about 2 to 10 hours |
| Full extract with `getPosts` | about 1 to 4 days |

Which end of the lookup range you hit depends on whether you remove duplicate target URIs, and on whether you stay on public AppView instead of the PDS 3,000 per 5 minutes cap.

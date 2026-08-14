# Expected files

The input file is `experiments/data_request_2026_08_14/greedy10_dedup_members.csv`. It lists 8,431 account ids (DIDs). A DID is a stable Bluesky account id. Generated files go under `experiments/data_request_2026_08_14/data/<run_timestamp>/`.

AppView is Bluesky's public API for profiles and posts. Hydration means looking up a post URI on AppView so `posts.csv` can hold the post text, media flags, language, author, and engagement counts.

Likes, reposts, quotes, and replies live in their own files and store join keys, not a full copy of the post on every row. Join those files to `posts.csv` on `post_uri` (or `quoted_post_uri` / `parent_post_uri`). Join person fields to `profiles.csv` on `did` or `actor_did`.

The time window is the 365 days ending when the job starts. Follows between two members of the list are the follows that still exist when the job runs, and they stand in for followers and followees at the end of the window. Follow actions during the window are follow records created in that window that still exist. If someone followed and then unfollowed, the public repo no longer has that follow, so the row will not appear. Unfollows and deletions are not generated.

Saves (bookmarks) are private. `saves.csv` is written with a header and zero rows.

## File catalog

| File | One row is | Request items | Expected rows |
|---|---|---|---|
| `greedy10_dedup_members.csv` | one cohort DID (input, not generated) | input | 8,431 |
| `profiles.csv` | one cohort member | 1, 10, 11, 14, 15, 16 | 8,431 attempted |
| `posts.csv` | one unique post URI we have (cohort-authored during the window, plus liked, reposted, quoted, and reply-target posts we looked up) | per-post fields; join target for 2 to 7 | unique URIs |
| `original_posts.csv` | one post that is not a reply, written by a cohort member during the window | 2 | originals during the window |
| `likes.csv` | one like during the window | 3 | likes during the window |
| `reposts.csv` | one repost during the window | 4 | reposts during the window |
| `quotes.csv` | one quote during the window | 5 | quotes during the window |
| `replies.csv` | one reply during the window | 6 | replies during the window |
| `saves.csv` | one save during the window | 7 | 0 (header only) |
| `follow_edges.csv` | one follow that still exists, where both ends are in the cohort | 8 and 9 | current follows inside the cohort |
| `follow_actions.csv` | one follow created during the window that still exists | 12 | outbound follows during the window that still exist |
| `fetch_errors.csv` | one failed DID or failed post lookup | ops | failures only |
| `run_metadata.json` | one object for the run | run bookkeeping | 1 object |

Item 13 (unfollows) is omitted on purpose.

## Request item to file

| Nick item | File | How to read it |
|---|---|---|
| 1 Account creation date | `profiles.csv` | `account_created_at` (profile-record `createdAt` only; never inferred from first post) |
| 2 Original posts | `original_posts.csv` joined to `posts.csv` | Join `post_uri` |
| 3 Posts liked | `likes.csv` joined to `posts.csv` | Join `post_uri` |
| 4 Posts reposted | `reposts.csv` joined to `posts.csv` | Join `post_uri` |
| 5 Posts quoted | `quotes.csv` joined to `posts.csv` | Quote body: join `post_uri`. Quoted post: join `quoted_post_uri` |
| 6 Posts replied to | `replies.csv` joined to `posts.csv` | Reply body: join `post_uri`. Parent post: join `parent_post_uri` |
| 7 Posts saved | `saves.csv` | Header only, because bookmarks are private |
| 8 Cohort followers at end of window | `follow_edges.csv` | Rows where `followee_did` = member |
| 9 Cohort followees at end of window | `follow_edges.csv` | Rows where `follower_did` = member |
| 10 Latest follower count | `profiles.csv` | `followers_count` (AppView) |
| 11 Latest followee count | `profiles.csv` | `followees_count` (AppView) |
| 12 Follow actions in window | `follow_actions.csv` | Follows that still exist, with `created_at` in the window |
| 13 Unfollow actions | (omitted) | Out of scope |
| 14 Current bio | `profiles.csv` | `bio` |
| 15 Handle | `profiles.csv` | `handle` |
| 16 Display name | `profiles.csv` | `display_name` |

A quote that is not also a reply appears in both `original_posts.csv` and `quotes.csv`. The quote post and the quoted post both have rows in `posts.csv` when the AppView lookup succeeds.

## Columns

### `greedy10_dedup_members.csv` (input)

| Column | Type | Source | Meaning |
|---|---|---|---|
| `did` | string | input | Stable account id |
| `n_pools` | int | input | How many of the 10 seed pools include this DID |
| `seeds` | string | input | Seed handles whose pools include this DID, joined with semicolons |

### `profiles.csv`

| Column | Type | Source | Meaning |
|---|---|---|---|
| `did` | string | input | Cohort member DID |
| `handle` | string \| null | AppView getProfile | Current handle (can change) |
| `display_name` | string \| null | AppView / profile record | Current display name |
| `bio` | string \| null | AppView `description` | Current bio |
| `account_created_at` | datetime \| null | profile `createdAt` | Profile-record createdAt only |
| `window_start` | datetime | run config | Inclusive start of the 12-month window |
| `window_end` | datetime | run config | End bound (run start) |
| `followers_count` | int \| null | AppView `followersCount` | Latest total followers across Bluesky |
| `followees_count` | int \| null | AppView `followsCount` | Latest total followees across Bluesky |
| `n_pools` | int | input | Copied from the member list |
| `seeds` | string | input | Copied from the member list |

### `posts.csv`

Primary key: `post_uri`. The file includes posts a cohort member wrote during the window, and every like, repost, quote, or reply target we tried to look up. Referenced posts may be older than the window and may be written by accounts outside the cohort. If AppView no longer has the post, keep the URI and leave the other fields null (`hydration_status` is not `ok`).

| Column | Type | Source | Meaning |
|---|---|---|---|
| `post_uri` | string | record / AppView | AT-URI (join key). An AT-URI is Bluesky's stable id for a record. |
| `post_cid` | string \| null | record / AppView | Content hash of this version of the post |
| `author_did` | string \| null | AppView / repo | Post author |
| `author_handle` | string \| null | AppView | Handle at lookup time |
| `author_display_name` | string \| null | AppView | Display name at lookup time |
| `created_at` | datetime \| null | `record.createdAt` | Post timestamp |
| `indexed_at` | datetime \| null | AppView `indexedAt` | When AppView last indexed it |
| `text` | string \| null | `record.text` | Post body |
| `post_type` | `original` \| `reply` \| null | derived from reply pointer | Original vs item in a thread |
| `has_image` | bool \| null | embed | Images present |
| `has_video` | bool \| null | embed | Video present |
| `langs` | string \| null | `record.langs` | Language codes, joined with semicolons |
| `like_count` | int \| null | AppView `likeCount` | Likes at lookup time |
| `reply_count` | int \| null | AppView `replyCount` | Replies at lookup time |
| `repost_count` | int \| null | AppView `repostCount` | Reposts at lookup time |
| `quote_count` | int \| null | AppView `quoteCount` | Quotes at lookup time |
| `save_count` | int \| null | AppView `bookmarkCount` | Saves at lookup time |
| `hydration_status` | `ok` \| `not_found` \| `failed` \| `repo_only` | run | `repo_only` means the text came from getRepo, and AppView was not used or was not needed for text |

### `original_posts.csv`

| Column | Type | Source | Meaning |
|---|---|---|---|
| `actor_did` | string | post author | Cohort member who wrote the post |
| `post_uri` | string | repo | Join to `posts.csv` |

### `likes.csv`

| Column | Type | Source | Meaning |
|---|---|---|---|
| `actor_did` | string | like record repo | Cohort member who liked |
| `like_uri` | string | `app.bsky.feed.like` | AT-URI of the like record |
| `like_created_at` | datetime | like `createdAt` | When they liked |
| `post_uri` | string | like `subject.uri` | Join to `posts.csv` (the liked post) |

### `reposts.csv`

| Column | Type | Source | Meaning |
|---|---|---|---|
| `actor_did` | string | repost record repo | Cohort member who reposted |
| `repost_uri` | string | `app.bsky.feed.repost` | AT-URI of the repost record |
| `repost_created_at` | datetime | repost `createdAt` | When they reposted |
| `post_uri` | string | repost `subject.uri` | Join to `posts.csv` (the reposted post) |

### `quotes.csv`

| Column | Type | Source | Meaning |
|---|---|---|---|
| `actor_did` | string | quote author | Cohort member who quoted |
| `post_uri` | string | quote post | Join to `posts.csv` for what they said |
| `quoted_post_uri` | string \| null | embed record | Join to `posts.csv` for the post that was quoted |

### `replies.csv`

Parent is `reply.parent` (the post they replied to), not necessarily the thread root.

| Column | Type | Source | Meaning |
|---|---|---|---|
| `actor_did` | string | reply author | Cohort member who replied |
| `post_uri` | string | reply post | Join to `posts.csv` for what they said |
| `parent_post_uri` | string \| null | `record.reply.parent` | Join to `posts.csv` for the post replied to |
| `reply_root_uri` | string \| null | `record.reply.root` | Thread root URI. Include a `posts.csv` row for it only if we looked it up. Looking it up is not required. |

### `saves.csv`

Same columns as `likes.csv`. Expected row count: 0.

| Column | Type | Source | Meaning |
|---|---|---|---|
| `actor_did` | string | n/a | Would be the cohort member who saved |
| `save_uri` | string | n/a | Would be the bookmark record URI |
| `save_created_at` | datetime | n/a | Would be when they saved |
| `post_uri` | string | n/a | Would join to `posts.csv` |

### `follow_edges.csv`

Snapshot at run time. One file answers both "followers within collected profiles" and "followees within collected profiles."

| Column | Type | Source | Meaning |
|---|---|---|---|
| `follower_did` | string | `app.bsky.graph.follow` | Cohort member who follows |
| `followee_did` | string | follow `subject` | Cohort member who is followed |
| `follow_uri` | string | follow record | AT-URI of the follow record that still exists |
| `follow_created_at` | datetime \| null | follow `createdAt` | When that follow was created (may be before the window) |

### `follow_actions.csv`

The followed account does not need to be in the cohort.

| Column | Type | Source | Meaning |
|---|---|---|---|
| `actor_did` | string | follow record repo | Cohort member who followed |
| `follow_uri` | string | `app.bsky.graph.follow` | AT-URI of the follow record |
| `followed_did` | string | follow `subject` | DID that was followed |
| `created_at` | datetime | follow `createdAt` | When the follow happened |
| `followed_in_cohort` | bool | derived | True if `followed_did` is in the member list |

### `fetch_errors.csv`

| Column | Type | Source | Meaning |
|---|---|---|---|
| `did` | string \| null | run | Cohort DID when the failure is about an account |
| `uri` | string \| null | run | Post URI when the failure is about looking up a post |
| `stage` | string | run | `profile` \| `getRepo` \| `decode` \| `getPosts` \| `follows` |
| `error` | string | run | Short reason (`RepoNotFound`, `notFoundPost`, timeout, and similar) |

### `run_metadata.json`

| Field | Type | Meaning |
|---|---|---|
| `run_timestamp` | datetime | When the job started |
| `window_start` / `window_end` | datetime | Bounds used for filters |
| `cohort_size` | int | 8,431 |
| `record_counts` | object | Row counts per CSV |
| `source_methods` | object | getRepo vs AppView vs getPosts |
| `unavailable_fields` | string[] | saved posts (private); unfollows and deletions (out of scope) |

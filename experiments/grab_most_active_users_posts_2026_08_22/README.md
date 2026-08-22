# Most active users' recent posts

**Date:** 2026-08-22
**Status:** Complete

Pulls posts from `bluesky_raw.posts` for later work on high-volume authors.

The query keeps posts with `created_at` on or after 2026-08-02 (strictly after 2026-08-01). It ranks authors by post count, keeps the top 250, and then keeps each of those authors' 100 most recent posts. Ties on count use `did`. Ties on recency use `uri`. The extract also stores `user_post_count` and `recency_rank`.

## Run

```bash
PYTHONPATH=. uv run python \
  experiments/grab_most_active_users_posts_2026_08_22/query_db.py
```

Writes `posts.parquet` in this folder. A second run skips the query if that file already exists.

The checked-in extract has 25,000 posts from 250 authors (100 each). Author post counts after 2026-08-01 range from 3,706 to 515,575. The 100 most recent posts per author fall between 2026-08-12 and 2026-08-22.

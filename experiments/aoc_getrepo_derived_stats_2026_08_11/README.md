# AOC getRepo derived stats (2026-08-11)

Collect AOC plus her 50 most recent followers, download each repo with
`com.atproto.sync.getRepo`, and derive a fixed 6-month stats document per
member. Fields the repo snapshot cannot prove are written as null.

## Run

From the repo root:

```bash
PYTHONPATH=. uv run python experiments/aoc_getrepo_derived_stats_2026_08_11/main.py
```

Outputs land under `experiments/aoc_getrepo_derived_stats_2026_08_11/data/<timestamp>/`.

## Always null

- `saved_posts` (private bookmarks)
- `unfollow_actions` (deletes leave no snapshot trail)
- `quoted_post_body` and `parent_post_body` (no `getPosts` hydration)

## Sources

- Discovery and scalar follower counts: public AppView
- Repos: relay `getRepo`
- Decode: `experimentation.aoc_followers_backfill.mst.decode_repo`

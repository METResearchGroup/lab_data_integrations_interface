# AOC posts getRepo metrics

Collect at least 50 of AOC's latest Bluesky posts via public `getAuthorFeed`, load her repository once with relay `getRepo`, derive structural fields from the repo, then enrich likes, replies, reposts, quotes, and saves via AppView `getPosts`.

The `deleted` column is always `unknown`, because a single `getRepo` snapshot does not provide deletion timestamps.

```bash
PYTHONPATH=. uv run python experimentation/aoc_posts_getrepo_metrics/main.py
```

Outputs land under `experimentation/aoc_posts_getrepo_metrics/data/<timestamp>/` as `posts_metrics.csv` and `metadata.json`.

```bash
uv run pytest tests/experimentation/aoc_posts_getrepo_metrics/ -q
```

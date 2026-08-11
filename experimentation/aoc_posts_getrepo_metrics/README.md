# AOC posts getRepo metrics

Collect at least 50 of AOC's latest Bluesky posts via public `getAuthorFeed`, load her repository once with relay `getRepo`, and write getRepo-only metrics to CSV.

Engagement counts and deletion timestamps stay empty, because they are not available from a single `getRepo` export. The `deleted` column is always `unknown`.

```bash
PYTHONPATH=. uv run python experimentation/aoc_posts_getrepo_metrics/main.py
```

Outputs land under `experimentation/aoc_posts_getrepo_metrics/data/<timestamp>/` as `posts_metrics.csv` and `metadata.json`.

```bash
uv run pytest tests/experimentation/aoc_posts_getrepo_metrics/ -q
```

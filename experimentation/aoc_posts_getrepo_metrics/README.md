# AOC posts getRepo metrics

Collect at least 50 of AOC's latest Bluesky posts via public `getAuthorFeed`, load her repository once with relay `getRepo`, and write getRepo-only metrics to CSV.

```bash
PYTHONPATH=. uv run python experimentation/aoc_posts_getrepo_metrics/main.py
```

Outputs land under `experimentation/aoc_posts_getrepo_metrics/data/<timestamp>/`.

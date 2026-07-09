# Reddit subreddit post & comment fetch experiment (2026-05-23)

## Summary

This experiment validates end-to-end Reddit data access via [PRAW](https://praw.readthedocs.io/) before wiring Reddit into the lab's ingestion pipeline ([Epic: Implement data ingestion pipeline](https://github.com/METResearchGroup/lab_data_integrations_interface/issues/53)). It collects **10 hot posts** from each of six political subreddits (`Conservative`, `Republican`, `AskConservatives`, `politics`, `liberal`, `democrats`) and, for each post, up to **100 eligible comments** in Reddit's default display order.

**Motivation:** Downstream political-stance and mirrorview analysis needs post text plus linked comment threads. Fetching entire threads is expensive and noisy, so the experiment caps collection at 100 qualifying comments per post and filters out stickied comments, mod-distinguished comments, and bodies shorter than 30 characters.

**Key findings:**

- PRAW script-app authentication via root `.env` credentials (`REDDIT_CLIENT_ID`, `REDDIT_SECRET`, `REDDIT_USERNAME`, `REDDIT_PASSWORD`) works for one-shot collection.
- A depth-first comment walk with `replace_more` expansion yields comments in Reddit display order while respecting the per-post cap.
- Comment yield varies widely by subreddit even with identical post limits — `r/politics` produced the most eligible comments in the live run, while `r/liberal` produced the fewest.
- The initial post-only fetch batch (`data/2026_05_23-15:52:04/`) was removed from the repo because it predated comment collection.

## Results

Live run committed in [PR #32](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/32): `data/2026_05_24-16:18:21/` (sync timestamp `2026_05_24-16:18:21`).

| Metric | Value |
|--------|-------|
| Subreddits | 6 |
| Posts per subreddit | 10 |
| Total posts | 60 |
| Max comments per post | 100 |
| Min comment body length | 30 characters |
| **Total comments** | **1,678** |

| Subreddit | Posts | Comments |
|-----------|------:|---------:|
| conservative | 10 | 92 |
| republican | 10 | 59 |
| askconservatives | 10 | 527 |
| politics | 10 | 802 |
| liberal | 10 | 36 |
| democrats | 10 | 162 |

## How to Run

**Prerequisites:** Reddit API credentials in the repo-root `.env` (see [HOW_TO_ADD_NEW_BATCH_DATA_JOB.md](../../docs/runbooks/HOW_TO_ADD_NEW_BATCH_DATA_JOB.md)). Use straight ASCII quotes in `.env` values — smart/curly quotes break `python-dotenv` parsing.

From repo root:

```bash
uv sync
PYTHONPATH=. uv run python experiments/reddit_fetch_data_2026_05_23/main.py
```

**Expected output:**

- New directory: `experiments/reddit_fetch_data_2026_05_23/data/<sync_timestamp>/`
- Six post CSVs (`{subreddit}.csv`) with 10 rows each
- Six comment CSVs (`{subreddit}_comments.csv`) with eligible comments linked to posts
- `metadata.json` with collection config, per-subreddit counts, and file map
- Stdout summary per subreddit: `N posts, M comments written to ...`

**Optional verification** (after a live run):

```bash
uv sync --group dev && uv run pre-commit run --all-files
uv sync --extra testing && uv run pytest tests/ -v
```

## Files

| File / path | Purpose |
|-------------|---------|
| [`main.py`](main.py) | Entry point. Sets `sync_timestamp`, iterates `SUBREDDITS`, writes post/comment CSVs and `metadata.json`. Constants: `POSTS_PER_SUBREDDIT=10`, `COMMENTS_PER_POST=100`, `MIN_COMMENT_BODY_LENGTH=30`. |
| [`reddit_client.py`](reddit_client.py) | PRAW client helpers: `init_reddit()`, `submission_to_row()`, `fetch_post_comments()` (DFS walk + eligibility filter), `fetch_subreddit_posts()` (returns post and comment rows). Defines CSV schemas in `CSV_FIELDNAMES` and `COMMENT_CSV_FIELDNAMES`. |
| [`__init__.py`](__init__.py) | Package marker so `experiments.reddit_fetch_data_2026_05_23` imports work with `PYTHONPATH=.`. |
| [`data/<sync_timestamp>/`](data/) | Timestamped fetch output. Each run creates a new subfolder. |
| `data/2026_05_24-16:18:21/metadata.json` | Run manifest: subreddit list, post/comment counts, config (`comments_per_post_max`, `min_comment_body_length`), and filename maps. Start here to understand a committed dataset. |
| `data/2026_05_24-16:18:21/{subreddit}.csv` | Post rows: `reddit_id`, title, `selftext`, author, score, engagement fields, `sync_timestamp`. |
| `data/2026_05_24-16:18:21/{subreddit}_comments.csv` | Comment rows: `post_reddit_id`, `comment_id`, `body`, `depth`, `comment_rank` (1–100 per post), parent linkage, `sync_timestamp`. |

## References

- [PR #28 — Add Reddit subreddit post fetch experiment](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/28) (initial post collection; merged 2026-05-24)
- [PR #32 — Add Reddit comment collection to fetch experiment](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/32) (comment fetching + live data; merged 2026-05-24)
- [Issue #53 — [Epic] Implement data ingestion pipeline](https://github.com/METResearchGroup/lab_data_integrations_interface/issues/53) (cross-referenced by PR #28)
- Implementation plans: [`docs/plans/2026-05-23_reddit_fetch_data_482917/plan.md`](../../docs/plans/2026-05-23_reddit_fetch_data_482917/plan.md), [`docs/plans/2026-05-24_reddit_fetch_comments_738492/plan.md`](../../docs/plans/2026-05-24_reddit_fetch_comments_738492/plan.md)

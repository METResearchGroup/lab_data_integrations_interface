# X Keyword Fetch Experiment (2026-06-01)

## Summary

This experiment validates **X API v2 recent search** for Mirrorview political keywords before promoting ingestion into `data_platform/`. It follows the same one-shot script pattern as [`experiments/reddit_fetch_data_2026_05_23/`](../reddit_fetch_data_2026_05_23/main.py): authenticate with a Bearer Token, fetch posts per keyword with filters for original English posts only, and write normalized CSV + metadata under a timestamped output directory.

**Motivation:** Mirrorview analysis needs X/Twitter posts aligned with political topic keywords, but production ingestion did not yet exist. This POC proves the API contract, query shape, normalization schema, and orchestration at low cost (~$0.50 for 100 posts) without wiring into `data_platform/`.

**Key findings:**

- X API v2 recent search with Tweepy Bearer auth successfully returns real, on-topic posts for all 10 Mirrorview keyword clusters tested.
- The query pattern `"<keyword>" lang:en -is:reply -is:retweet -is:quote` reliably filters to original English posts.
- A global 100-post cap with per-keyword targets (10 × 10) works as intended; metadata `counts_by_keyword` matches CSV row counts.
- Rate-limit handling (`wait_on_rate_limit=True`) and per-keyword error isolation (continue loop on failure) were added after the initial smoke test to harden the script.
- Results from this experiment informed the production Twitter ingestion pipeline added in [PR #47](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/47).

## Results

Smoke-test run committed in-repo: `data/2026_06_01-14:32:18/`

| Metric | Value |
|---|---|
| Run timestamp | `2026_06_01-14:32:18` |
| API | X API v2 (`/2/tweets/search/recent`) |
| Auth | Bearer Token (app-only) |
| Total post cap | 100 |
| Posts per keyword target | 10 |
| Keywords queried | 10 |
| **Total posts fetched** | **100** |
| Posts per keyword | 10 each (all keywords hit target) |
| Filters | Original posts only; English (`lang:en`); excludes reply, retweet, quote |
| Estimated API cost | ~$0.50 (100 posts × ~$0.005/post) |
| Unit tests | 5 passed (mocked, no live API) |
| Sample verification | [Example tweet](https://x.com/MagaMalinois/status/2061455641021927758) manually confirmed real |

### Per-keyword counts

| Keyword | Posts |
|---|---|
| gun control | 10 |
| climate change | 10 |
| abortion | 10 |
| immigration | 10 |
| second amendment | 10 |
| reproductive rights | 10 |
| border security | 10 |
| renewable energy | 10 |
| pro-life | 10 |
| DACA | 10 |

## How to Run

### Prerequisites

1. Create an X developer app at [console.x.com](https://console.x.com) and copy the **Bearer Token**.
2. Add to repo-root `.env`:

   ```bash
   X_BEARER_TOKEN=your_bearer_token_here
   ```

   (`X_CONSUMER_KEY` and `X_SECRET_KEY` are registered in `lib/load_env_vars.py` but not required for this experiment.)

### Fetch posts

From repo root:

```bash
PYTHONPATH=. uv run python experiments/x_fetch_data_2026_06_01/main.py
```

Output is written to `experiments/x_fetch_data_2026_06_01/data/<sync_timestamp>/` with `posts.csv` and `metadata.json`. The script prints per-keyword counts as it runs.

### Run unit tests

```bash
uv run pytest tests/experiments/x_fetch_data_2026_06_01/ -q
```

### Lint

```bash
uv run ruff check experiments/x_fetch_data_2026_06_01/ tests/experiments/x_fetch_data_2026_06_01/
```

## Files

| File | Description |
|---|---|
| [`main.py`](main.py) | Entry point. Defines `KEYWORDS` (10 Mirrorview topic clusters), `TOTAL_POST_CAP` (100), and `POSTS_PER_KEYWORD` (10). Loops keywords, calls `fetch_posts_for_keyword`, writes `posts.csv` and `metadata.json` to `data/<sync_timestamp>/`. |
| [`x_client.py`](x_client.py) | Tweepy client helpers: `init_x_client()` (Bearer auth), `build_query()` (recent-search query with lang/exclusion filters), `fetch_posts_for_keyword()` (paginated search with `next_token`), `tweet_to_row()` (normalizes tweets to `CSV_FIELDNAMES` schema). |
| [`__init__.py`](__init__.py) | Empty package marker. |
| [`data/<sync_timestamp>/posts.csv`](data/2026_06_01-14:32:18/posts.csv) | Normalized tweet rows. Columns: `tweet_id`, `text`, `author_id`, `username`, `created_at`, engagement metrics, `url`, `keyword`, `sync_timestamp`. |
| [`data/<sync_timestamp>/metadata.json`](data/2026_06_01-14:32:18/metadata.json) | Run metadata: API endpoint, caps, filters, keyword list, per-keyword counts, and file references. |
| [`tests/experiments/x_fetch_data_2026_06_01/test_x_client.py`](../../tests/experiments/x_fetch_data_2026_06_01/test_x_client.py) | Mocked unit tests for query building, tweet normalization, and pagination (no live API calls). |
| [`docs/plans/2026-06-01_x_keyword_fetch_experiment_482912/plan.md`](../../docs/plans/2026-06-01_x_keyword_fetch_experiment_482912/plan.md) | Implementation plan with interface contracts, data flow, and verification checklist. |

## References

- [PR #46 — Add X keyword fetch experiment](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/46) — merged 2026-06-01
- [PR #47 — Add Twitter Mirrorview ingestion pipeline](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/47) — follow-up that promoted this pattern into `data_platform/`
- [Implementation plan](../../docs/plans/2026-06-01_x_keyword_fetch_experiment_482912/plan.md)

No GitHub issues were linked to PR #46.

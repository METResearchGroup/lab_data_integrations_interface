# How to Add a New Batch Data Job

A batch job requires exactly two YAML files: an ingestion config and a curate config. Preprocessing and feature generation require no per-job config — they run automatically for any `dataset_id`.

Supported platforms: **bluesky**, **reddit**, **twitter**. The config structure is the same across platforms; the fetch-specific fields differ. See existing examples for each:

- Bluesky: [`data_platform/ingestion/configs/bluesky/mirrorview.yaml`](../../data_platform/ingestion/configs/bluesky/mirrorview.yaml), [`data_platform/curate/configs/bluesky/mirrorview.yaml`](../../data_platform/curate/configs/bluesky/mirrorview.yaml)
- Reddit: [`data_platform/ingestion/configs/reddit/mirrorview.yaml`](../../data_platform/ingestion/configs/reddit/mirrorview.yaml), [`data_platform/curate/configs/reddit/mirrorview.yaml`](../../data_platform/curate/configs/reddit/mirrorview.yaml)
- Twitter: [`data_platform/ingestion/configs/twitter/mirrorview.yaml`](../../data_platform/ingestion/configs/twitter/mirrorview.yaml), [`data_platform/curate/configs/twitter/mirrorview.yaml`](../../data_platform/curate/configs/twitter/mirrorview.yaml)

---

## Step 1: Create the ingestion YAML

**File:** `data_platform/ingestion/configs/<platform>/<job_name>.yaml`

Fields shared across all platforms:

- **`dataset_id`** — fixed UUID linking all pipeline stages. Generate once, never change. Must match the curate config. The ID should be prefixed with the platform name (e.g. `bluesky_<uuid>`, `reddit_<uuid>`).
  ```bash
  python -c "import uuid; print('bluesky_' + str(uuid.uuid4()))"
  ```
- **`output_format`** — `parquet` or `csv`. This single value propagates automatically to all downstream stages via `dataset.json`. Use `parquet` for large datasets; `csv` if you need plain text output.

The fetch-specific fields (keywords, subreddits, limits, etc.) differ per platform — refer to the existing mirrorview configs linked above as the reference for each.

---

## Step 2: Create the curate YAML

**File:** `data_platform/curate/configs/<platform>/<job_name>.yaml`

- **`stem`** — base name for the output file. The extension (`.parquet` or `.csv`) is appended automatically based on `output_format` from the ingestion YAML.
- **`filters`** — rows are kept only if they pass all conditions. Each filter specifies a `column`, an `op` (`eq`, `neq`, `in`, `gt`, `lt`), and a `value`.

The curate config is identical in structure across all platforms. The available filter columns come from the features defined in [`data_platform/generate_features/registry.py`](../../data_platform/generate_features/registry.py). The exact column names and possible values for each feature are in the output model (`*Model` class) inside each feature's `generate_feature.py`

---

## Step 3: Run the pipeline

Currently only Bluesky has a full orchestration script. For Bluesky:

```bash
PYTHONPATH=. uv run python data_platform/orchestration/orchestrate_bluesky.py \
    --ingestion-config <job_name>.yaml \
    --curate-config <job_name>.yaml
```

The pipeline runs 4 stages in sequence:

1. **Ingestion** — fetches posts from the platform API, writes raw records under `data/<platform>/<dataset_id>/raw/<timestamp>/`
2. **Preprocessing** — filters out non-English posts, URLs, phone numbers, and too-short posts
3. **Feature generation** — calls OpenAI (6 features) and Google Perspective API (toxicity) to label all posts; writes one CSV per feature under `features/`
4. **Curation** — joins all feature CSVs with preprocessed posts, applies your filters, writes final output under `curated/<timestamp>/`

---

## Step 4: Find the output

```
data_platform/data/<platform>/<dataset_id>/curated/<timestamp>/<stem>.<parquet|csv>
```

---

## Resuming an interrupted run

If the pipeline is killed during feature generation, re-run the exact same command. Ingestion and preprocessing re-run quickly (~15s), and feature generation skips already-labeled posts and picks up where it left off. No data is lost.

---

## Required environment variables

Ensure `.env` at the repo root contains the keys for whichever platform and APIs you are using:

```
# Bluesky
BLUESKY_HANDLE=<your-handle>.bsky.social
BLUESKY_PASSWORD=<app-password>

# Reddit
REDDIT_CLIENT_ID=<id>
REDDIT_SECRET=<secret>
REDDIT_USERNAME=<username>
REDDIT_PASSWORD=<password>

# Feature generation (all platforms)
OPENAI_API_KEY=<key>
GOOGLE_API_KEY=<key>
```

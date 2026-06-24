# Glue Table Schemas

Glue database: `lab_data_integrations_interface`
S3 bucket: `lab-data-integrations-interface`
Format: `STORED AS PARQUET` (parquet datasets only)

---

## bluesky_raw

**S3 prefix:** `s3://lab-data-integrations-interface/raw/`
**Partition columns:** `platform`, `dataset_id`, `run_dir`

| Column | Glue type |
|---|---|
| `uri` | `STRING` |
| `url` | `STRING` |
| `author_handle` | `STRING` |
| `text` | `STRING` |
| `created_at` | `STRING` |
| `like_count` | `BIGINT` |
| `repost_count` | `BIGINT` |
| `reply_count` | `BIGINT` |
| `quote_count` | `BIGINT` |

---

## bluesky_preprocessed

**S3 prefix:** `s3://lab-data-integrations-interface/preprocessed/platform=bluesky/`
**Partition columns:** `dataset_id`, `run_dir`

Same schema as `bluesky_raw` — preprocessing doesn't add or drop columns.

| Column | Glue type |
|---|---|
| `uri` | `STRING` |
| `url` | `STRING` |
| `author_handle` | `STRING` |
| `text` | `STRING` |
| `created_at` | `STRING` |
| `like_count` | `BIGINT` |
| `repost_count` | `BIGINT` |
| `reply_count` | `BIGINT` |
| `quote_count` | `BIGINT` |

---

## Feature tables

All feature tables share a common `uri` + `label_timestamp` header.
Partition column: `dataset_id` only (no `run_dir` — features are flat, one file per feature per dataset).
Each table has its own S3 root under `feature={name}/` so partitions are isolated.

### bluesky_features_is_political

**S3 prefix:** `s3://lab-data-integrations-interface/features/platform=bluesky/feature=is_political/`

| Column | Glue type |
|---|---|
| `uri` | `STRING` |
| `label_timestamp` | `STRING` |
| `is_political` | `BOOLEAN` |

### bluesky_features_is_news_or_opinion

**S3 prefix:** `s3://lab-data-integrations-interface/features/platform=bluesky/feature=is_news_or_opinion/`

| Column | Glue type |
|---|---|
| `uri` | `STRING` |
| `label_timestamp` | `STRING` |
| `category` | `STRING` |

### bluesky_features_is_likely_spam

**S3 prefix:** `s3://lab-data-integrations-interface/features/platform=bluesky/feature=is_likely_spam/`

| Column | Glue type |
|---|---|
| `uri` | `STRING` |
| `label_timestamp` | `STRING` |
| `is_likely_spam` | `BOOLEAN` |

### bluesky_features_is_self_contained

**S3 prefix:** `s3://lab-data-integrations-interface/features/platform=bluesky/feature=is_self_contained/`

| Column | Glue type |
|---|---|
| `uri` | `STRING` |
| `label_timestamp` | `STRING` |
| `is_self_contained` | `BOOLEAN` |

### bluesky_features_is_structurally_complete

**S3 prefix:** `s3://lab-data-integrations-interface/features/platform=bluesky/feature=is_structurally_complete/`

| Column | Glue type |
|---|---|
| `uri` | `STRING` |
| `label_timestamp` | `STRING` |
| `is_structurally_complete` | `BOOLEAN` |

### bluesky_features_is_toxic_tiered

**S3 prefix:** `s3://lab-data-integrations-interface/features/platform=bluesky/feature=is_toxic_tiered/`

| Column | Glue type |
|---|---|
| `uri` | `STRING` |
| `label_timestamp` | `STRING` |
| `toxicity_prob` | `DOUBLE` |
| `toxicity_tier` | `STRING` |

### bluesky_features_political_stance

**S3 prefix:** `s3://lab-data-integrations-interface/features/platform=bluesky/feature=political_stance/`

| Column | Glue type |
|---|---|
| `uri` | `STRING` |
| `label_timestamp` | `STRING` |
| `political_stance` | `STRING` |

---

## bluesky_curated

**S3 prefix:** `s3://lab-data-integrations-interface/curated/platform=bluesky/`
**Partition columns:** `dataset_id`, `run_dir`

Wide table: preprocessed post columns joined with one label column per feature (via `uri`).
Column aliases match `FEATURE_WIDE_COLUMNS` in `data_platform/curate/consolidate.py`.

| Column | Glue type |
|---|---|
| `uri` | `STRING` |
| `url` | `STRING` |
| `author_handle` | `STRING` |
| `text` | `STRING` |
| `created_at` | `STRING` |
| `like_count` | `BIGINT` |
| `repost_count` | `BIGINT` |
| `reply_count` | `BIGINT` |
| `quote_count` | `BIGINT` |
| `news_or_opinion_category` | `STRING` |
| `is_political` | `BOOLEAN` |
| `is_likely_spam` | `BOOLEAN` |
| `is_self_contained` | `BOOLEAN` |
| `is_structurally_complete` | `BOOLEAN` |
| `toxicity_prob` | `DOUBLE` |
| `toxicity_tier` | `STRING` |
| `political_stance` | `STRING` |

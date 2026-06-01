# Curate political stance filter

## Overview

Mirrorview curation currently keeps opinion, political, self-contained, structurally complete records but does not require a partisan stance. We will tighten the mirrorview business rules so only records labeled `left` or `right` pass curation, then regenerate curated exports for the Reddit and Bluesky mirrorview datasets. The join layer already exposes `political_stance`; the filter engine already supports list membership via `op: in`. This is primarily a config + test + rerun task.

## Happy Flow

1. **Preprocessed records** live under `data_platform/data/{reddit|bluesky}/{dataset_id}/preprocessed/{timestamp}/`.
2. **Feature CSVs** (including `political_stance.csv`) live under `data_platform/data/{reddit|bluesky}/{dataset_id}/features/`.
3. `data_platform/curate/curate_reddit.py` / `data_platform/curate/curate_bluesky.py` load the latest preprocessed run and call `build_wide_table()` to LEFT JOIN all features (including `political_stance` via `FEATURE_WIDE_COLUMNS`).
4. `apply_rules()` applies YAML filters sequentially (AND), recording per-step counts.
5. **Updated filter chain** (after `is_political`, before quality gates):

```yaml
  - column: political_stance
    op: in
    value:
      - left
      - right
```

6. Filtered rows are written to `data_platform/data/{platform}/{dataset_id}/curated/{timestamp}/mirrorview.csv` with `metadata.json` documenting funnel stats.

## Manual Verification

- [ ] **Tests:** `PYTHONPATH=. uv run pytest tests/data_platform/curate/ -q` — all pass
- [ ] **Reddit curation:**

```bash
PYTHONPATH=. uv run python data_platform/curate/curate_reddit.py \
  --dataset-id reddit_f47ac10b-58cc-4372-a567-0e02b2c3d479 \
  --config mirrorview.yaml
```

  Expected stdout pattern: `curate_mirrorview: kept N of 10663 comments -> data_platform/data/reddit/.../curated/{timestamp}`

- [ ] **Bluesky curation:**

```bash
PYTHONPATH=. uv run python data_platform/curate/curate_bluesky.py \
  --dataset-id bluesky_f47ac10b-58cc-4372-a567-0e02b2c3d479 \
  --config mirrorview.yaml
```

  Expected stdout pattern: `curate_mirrorview: kept N of 785 posts -> ...`

- [ ] **Reddit metadata:** Open newest `data_platform/data/reddit/reddit_f47ac10b-58cc-4372-a567-0e02b2c3d479/curated/{timestamp}/metadata.json`
  - `filter_results` has **5** steps
  - Step 3: `column == "political_stance"`, `op == "in"`, `value == ["left", "right"]`
  - `row_counts.after_filters` < 3714

- [ ] **Bluesky metadata:** Same checks under `data_platform/data/bluesky/bluesky_f47ac10b-.../curated/{timestamp}/metadata.json`
  - `row_counts.after_filters` < 337

- [ ] **Export spot-check:** In each new `mirrorview.csv`, confirm `political_stance` column exists and every value is `left` or `right`.

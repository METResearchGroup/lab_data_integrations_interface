# is_toxic_tiered_v2

Opt-in Perspective API feature based on [`is_toxic_tiered`](../is_toxic_tiered/generate_feature.py).

## Rationale

`is_toxic_tiered` (v1) tiers on a single **TOXICITY** score with 0.1 / 0.7 cutoffs. That mostly answers "is this toxic?" rather than gradations of severity.

`is_toxic_tiered_v2` adds **SEVERE_TOXICITY** in the same API call. When broad toxicity is detected, severe toxicity distinguishes **medium** vs **high** harm.

| Feature | Inputs | Tier rule |
|---------|--------|-----------|
| `is_toxic_tiered` | `TOXICITY` only | low ≤ 0.1; high ≥ 0.7; else medium |
| `is_toxic_tiered_v2` | `TOXICITY` + `SEVERE_TOXICITY` | low if toxicity ≤ 0.5; high if toxicity > 0.5 and severe > 0.5; else medium |

## Usage

Explicit opt-in only:

```bash
PYTHONPATH=. uv run python data_platform/generate_features/generate_reddit_features.py \
  --dataset-id reddit_<uuid> \
  --features is_toxic_tiered_v2
```

v2 is **not** included in default feature generation runs and is **not** wired into curation unless added later.

## Output

CSV columns: `uri`, `label_timestamp`, `toxicity_prob`, `severe_toxicity_prob`, `toxicity_tier`.

## Notes

- Google is sunsetting the Perspective API at the end of 2026; plan migrations accordingly.
- Default `max_concurrency=80` may hit rate limits on large jobs; lower `--max-concurrency` for scale runs.

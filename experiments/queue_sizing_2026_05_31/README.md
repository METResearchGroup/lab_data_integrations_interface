# Queue sizing experiment (2026-05-31)

Estimates in-memory footprint of a Python `queue.Queue` holding dict records shaped like preprocessed posts: `index`, 50-character Faker `post` text, and a `date` timestamp from `lib.timestamp_utils.get_current_timestamp()`.

Size is measured by draining the queue and serializing the payload with `pickle` (approximate object-graph size, not exact RSS).

## Run

From repo root:

```bash
PYTHONPATH=. uv run python experiments/queue_sizing_2026_05_31/test_queue_sizing.py
```

## Results

Run date: 2026-05-31.

| Elements | Size (MB) | Bytes / element |
|----------|-----------|-----------------|
| 10 | 0.0007 | ~73 |
| 100 | 0.0069 | ~72 |
| 1,000 | 0.0699 | ~73 |
| 10,000 | 0.6980 | ~73 |
| 100,000 | 7.0418 | ~74 |

Scaling is approximately linear: ~73–74 bytes per queued record at these sizes, so 100k records land at roughly **7 MB** of serialized payload.

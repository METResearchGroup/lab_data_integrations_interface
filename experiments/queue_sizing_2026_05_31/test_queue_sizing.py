"""Measure in-memory queue footprint at increasing element counts.

Run from repo root:

    PYTHONPATH=. uv run python experiments/queue_sizing_2026_05_31/test_queue_sizing.py
"""

from __future__ import annotations

import pickle
from queue import Queue

from faker import Faker

from lib.timestamp_utils import get_current_timestamp

SIZES = (10, 100, 1000, 10000, 100000)


def queue_size_mb(queue: Queue) -> float:
    """Estimate queue payload size in megabytes via pickle serialization."""
    items: list[dict[str, object]] = []
    while not queue.empty():
        items.append(queue.get())
    return len(pickle.dumps(items)) / (1024 * 1024)


def main() -> None:
    faker = Faker()
    queue_num_elements_to_size: dict[int, float] = {}

    for size in SIZES:
        queue: Queue = Queue()
        for i in range(size):
            queue.put(
                {
                    "index": i,
                    "post": faker.text(max_nb_chars=50)[:50],
                    "date": get_current_timestamp(),
                }
            )

        size_mb = queue_size_mb(queue)
        print(f"size={size}: {size_mb:.4f} MB")
        queue_num_elements_to_size[size] = size_mb

    print("\nqueue_num_elements_to_size:")
    for num_elements, mb in queue_num_elements_to_size.items():
        print(f"  {num_elements}: {mb:.4f} MB")


if __name__ == "__main__":
    main()

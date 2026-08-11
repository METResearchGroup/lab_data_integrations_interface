"""Run DynamoDB single-put vs batch-write rate ablations and tear down keys.

Run from repo root:

    PYTHONPATH=. uv run python experiments/dynamodb_rates_2026_08_11/main.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from experiments.dynamodb_rates_2026_08_11.config import (
    AWS_REGION,
    ITEM_COUNT,
    TABLE_NAME,
)
from experiments.dynamodb_rates_2026_08_11.writes import (
    make_client,
    make_keys,
    run_batch_writes,
    run_single_puts,
    teardown_keys,
)
from lib.timestamp_utils import get_current_timestamp

DATA_DIR = Path(__file__).parent / "data"


def write_results(output_dir: Path, payload: dict[str, Any]) -> Path:
    """Write results.json under the run output directory.

    Parameters
    ----------
    output_dir
        Directory created for this run.
    payload
        Full results object to serialize.

    Returns
    -------
    Path
        Path to the written ``results.json`` file.
    """
    results_path = output_dir / "results.json"
    with results_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    return results_path


def main() -> None:
    """Time both write ablations, persist results, and always tear down keys."""
    client = make_client()
    run_id = get_current_timestamp()
    single_keys = make_keys(run_id=run_id, ablation="single", count=ITEM_COUNT)
    batch_keys = make_keys(run_id=run_id, ablation="batch", count=ITEM_COUNT)
    output_dir = DATA_DIR / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    single_result: dict[str, float | int] | None = None
    batch_result: dict[str, float | int] | None = None
    ablation_error: BaseException | None = None

    try:
        try:
            single_result = run_single_puts(client, single_keys)
            print(
                f"Ablation 1 ({ITEM_COUNT} PutItem) took "
                f"{single_result['duration_seconds']:.3f}s across "
                f"{single_result['http_calls']} HTTP calls"
            )

            batch_result = run_batch_writes(client, batch_keys)
            print(
                f"Ablation 2 ({ITEM_COUNT} BatchWriteItem) took "
                f"{batch_result['duration_seconds']:.3f}s across "
                f"{batch_result['http_calls']} HTTP calls"
            )
        except BaseException as exc:
            ablation_error = exc
    finally:
        teardown_result: dict[str, int | str] | None = None
        teardown_error: BaseException | None = None
        try:
            teardown_result = teardown_keys(client, single_keys + batch_keys)
            print(f"Teardown complete, {teardown_result['items_deleted']} keys deleted")
        except BaseException as exc:
            teardown_error = exc
            teardown_result = {
                "http_calls": 0,
                "items_deleted": 0,
                "error": str(exc),
            }

        write_error: BaseException | None = None
        try:
            write_results(
                output_dir,
                {
                    "run_id": run_id,
                    "table_name": TABLE_NAME,
                    "region": AWS_REGION,
                    "item_count": ITEM_COUNT,
                    "ablation_1_single_put": single_result,
                    "ablation_2_batch_write": batch_result,
                    "single_key_count": len(single_keys),
                    "batch_key_count": len(batch_keys),
                    "teardown": teardown_result,
                },
            )
        except BaseException as exc:
            write_error = exc

        if ablation_error is not None:
            if teardown_error is not None or write_error is not None:
                raise RuntimeError(
                    "Ablation failed and cleanup also failed "
                    f"(teardown={teardown_error!r}, write={write_error!r})"
                ) from ablation_error
            raise ablation_error
        if teardown_error is not None:
            raise teardown_error
        if write_error is not None:
            raise write_error


if __name__ == "__main__":
    main()

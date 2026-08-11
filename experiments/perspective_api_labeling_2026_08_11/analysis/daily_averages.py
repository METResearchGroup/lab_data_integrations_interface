"""Compute per-day average Perspective API label probabilities.

Writes analysis/outputs/daily/per_day_average.json and updates RESULTS.md.

Run from repo root:

    PYTHONPATH=. uv run python \\
        experiments/perspective_api_labeling_2026_08_11/analysis/daily_averages.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

EXPERIMENT_DIR = Path(__file__).resolve().parents[1]
LABELS_DIR = EXPERIMENT_DIR / "labels"
OUTPUT_DIR = Path(__file__).resolve().parent / "outputs" / "daily"
RESULTS_PATH = EXPERIMENT_DIR / "RESULTS.md"
DAYS = ("2026-08-09", "2026-08-10")


def _prob_columns(frame: pd.DataFrame) -> list[str]:
    return sorted(column for column in frame.columns if column.startswith("prob_"))


def compute_daily_averages() -> pd.DataFrame:
    rows: list[dict] = []
    for day in DAYS:
        path = LABELS_DIR / f"{day}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"Missing labels file: {path}")
        frame = pd.read_parquet(path)
        successful = frame[frame["was_successfully_labeled"] == True]  # noqa: E712
        if successful.empty:
            raise RuntimeError(f"No successfully labeled rows for {day}")
        averages = {"date": day}
        for column in _prob_columns(successful):
            averages[column] = float(successful[column].mean())
        rows.append(averages)
    return pd.DataFrame(rows)


def write_results_md(daily: pd.DataFrame) -> None:
    columns = ["date", *_prob_columns(daily)]
    table = daily[columns].copy()
    markdown_table = table.to_markdown(index=False, floatfmt=".6f")
    content = (
        "# Perspective API labeling results\n\n"
        "## Per-day average of each Perspective API label\n\n"
        "Averages are computed over successfully labeled posts only.\n\n"
        f"{markdown_table}\n"
    )
    RESULTS_PATH.write_text(content)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    daily = compute_daily_averages()
    output_path = OUTPUT_DIR / "per_day_average.json"
    records = daily.to_dict(orient="records")
    output_path.write_text(json.dumps(records, indent=2) + "\n")
    write_results_md(daily)
    print(f"wrote {output_path.relative_to(EXPERIMENT_DIR)}")
    print(f"wrote {RESULTS_PATH.relative_to(EXPERIMENT_DIR)}")


if __name__ == "__main__":
    main()

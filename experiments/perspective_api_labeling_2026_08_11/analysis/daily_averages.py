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


def _coverage_rows() -> list[dict]:
    """Return labeled vs posts counts per day for RESULTS.md context."""
    data_dir = EXPERIMENT_DIR / "data"
    rows: list[dict] = []
    for day in DAYS:
        labels_path = LABELS_DIR / f"{day}.parquet"
        posts_path = data_dir / f"{day}.parquet"
        n_posts = int(pd.read_parquet(posts_path, columns=["uri"]).shape[0])
        labels = pd.read_parquet(labels_path)
        n_labels = len(labels)
        n_success = int((labels["was_successfully_labeled"] == True).sum())  # noqa: E712
        rows.append(
            {
                "date": day,
                "posts": n_posts,
                "labeled": n_labels,
                "successfully_labeled": n_success,
                "coverage": n_labels / n_posts if n_posts else 0.0,
            }
        )
    return rows


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


def write_results_md(daily: pd.DataFrame, coverage: list[dict]) -> None:
    columns = ["date", *_prob_columns(daily)]
    table = daily[columns].copy()
    markdown_table = table.to_markdown(index=False, floatfmt=".6f")
    coverage_frame = pd.DataFrame(coverage)
    coverage_table = coverage_frame.to_markdown(index=False, floatfmt=".4f")
    incomplete = any(row["coverage"] < 0.995 for row in coverage)
    status = (
        "**Interim results.** Labeling is still in progress; averages below "
        "reflect only the posts labeled so far.\n\n"
        if incomplete
        else "Labeling coverage is complete for both days.\n\n"
    )
    content = (
        "# Perspective API labeling results\n\n"
        f"{status}"
        "## Coverage\n\n"
        f"{coverage_table}\n\n"
        "## Per-day average of each Perspective API label\n\n"
        "Averages are computed over successfully labeled posts only.\n\n"
        f"{markdown_table}\n\n"
        "## Per-hour averages\n\n"
        "See `analysis/outputs/hourly/per_hour_average.json` and the "
        "`*_per_hour_average.png` plots in the same directory.\n"
    )
    RESULTS_PATH.write_text(content)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    coverage = _coverage_rows()
    daily = compute_daily_averages()
    output_path = OUTPUT_DIR / "per_day_average.json"
    records = daily.to_dict(orient="records")
    output_path.write_text(json.dumps(records, indent=2) + "\n")
    write_results_md(daily, coverage)
    print(f"wrote {output_path.relative_to(EXPERIMENT_DIR)}")
    print(f"wrote {RESULTS_PATH.relative_to(EXPERIMENT_DIR)}")
    for row in coverage:
        print(
            f"coverage {row['date']}: {row['labeled']:,}/{row['posts']:,} "
            f"({row['coverage'] * 100:.2f}%)"
        )


if __name__ == "__main__":
    main()

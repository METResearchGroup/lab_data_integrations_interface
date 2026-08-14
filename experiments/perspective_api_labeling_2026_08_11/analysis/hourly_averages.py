"""Compute per-hour average Perspective API label probabilities and plots.

Joins labels to original posts for created_at, writes
analysis/outputs/hourly/per_hour_average.json and one PNG per attribute.

Run from repo root:

    PYTHONPATH=. uv run python \\
        experiments/perspective_api_labeling_2026_08_11/analysis/hourly_averages.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

EXPERIMENT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = EXPERIMENT_DIR / "data"
LABELS_DIR = EXPERIMENT_DIR / "labels"
OUTPUT_DIR = Path(__file__).resolve().parent / "outputs" / "hourly"
DAYS = ("2026-08-09", "2026-08-10")


def _prob_columns(frame: pd.DataFrame) -> list[str]:
    return sorted(column for column in frame.columns if column.startswith("prob_"))


def _attribute_name(prob_column: str) -> str:
    return prob_column.removeprefix("prob_")


def load_joined_labels() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for day in DAYS:
        labels_path = LABELS_DIR / f"{day}.parquet"
        posts_path = DATA_DIR / f"{day}.parquet"
        if not labels_path.exists():
            raise FileNotFoundError(f"Missing labels file: {labels_path}")
        if not posts_path.exists():
            raise FileNotFoundError(f"Missing posts file: {posts_path}")

        labels = pd.read_parquet(labels_path)
        labels = labels[labels["was_successfully_labeled"] == True]  # noqa: E712
        posts = pd.read_parquet(posts_path, columns=["uri", "created_at"])
        joined = labels.merge(posts, on="uri", how="inner")
        frames.append(joined)

    combined = pd.concat(frames, ignore_index=True)
    combined["created_at"] = pd.to_datetime(combined["created_at"], utc=True)
    combined["hour_key"] = combined["created_at"].dt.strftime("%Y-%m-%d:%H")
    return combined


def compute_hourly_averages(joined: pd.DataFrame) -> dict[str, dict[str, float]]:
    prob_columns = _prob_columns(joined)
    grouped = joined.groupby("hour_key", sort=True)[prob_columns].mean()
    result: dict[str, dict[str, float]] = {}
    for column in prob_columns:
        attribute = _attribute_name(column)
        series = grouped[column].dropna()
        result[attribute] = {str(hour): float(value) for hour, value in series.items()}
    return result


def write_hourly_plots(hourly: dict[str, dict[str, float]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for attribute, values in hourly.items():
        hours = sorted(values.keys())
        ys = [values[hour] for hour in hours]
        fig, ax = plt.subplots(figsize=(14, 4))
        ax.plot(hours, ys, linewidth=1.5)
        ax.set_title(f"{attribute} per-hour average")
        ax.set_xlabel("date+hour")
        ax.set_ylabel("average probability")
        ax.tick_params(axis="x", labelrotation=90, labelsize=7)
        fig.tight_layout()
        output_path = OUTPUT_DIR / f"{attribute}_per_hour_average.png"
        fig.savefig(output_path, dpi=120)
        plt.close(fig)
        print(f"wrote {output_path.relative_to(EXPERIMENT_DIR)}")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    joined = load_joined_labels()
    hourly = compute_hourly_averages(joined)
    output_path = OUTPUT_DIR / "per_hour_average.json"
    output_path.write_text(json.dumps(hourly, indent=2) + "\n")
    print(f"wrote {output_path.relative_to(EXPERIMENT_DIR)}")
    write_hourly_plots(hourly)


if __name__ == "__main__":
    main()

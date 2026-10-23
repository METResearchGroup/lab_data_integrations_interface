# Step 1: Consolidate existing Perspective labels

## Goal

Produce one Parquet file, `data/dataset.parquet`, that holds every post the Perspective API pipeline already labeled successfully, with one row per post.

## Scope

The only existing source of Perspective labels in this repository is `experiments/perspective_api_labeling_2026_08_11/labels/*.parquet`, one file per day. The label files are stored in Git LFS. Pull them locally before running anything in this step.

Step 1 only reads the label files and writes `data/dataset.parquet`. It does not touch the Perspective API client, does not call any external API, and does not yet split the data by label.

## Files to inspect

- [`feature_generation/perspective_api/schemas.py`](../../../feature_generation/perspective_api/schemas.py) for the exact column names on `PerspectiveApiLabelsModel`.
- [`experiments/perspective_api_labeling_2026_08_11/consolidate_labels.py`](../../../experiments/perspective_api_labeling_2026_08_11/consolidate_labels.py) for the existing pattern of concatenating and deduping Parquet files.
- [`experiments/perspective_api_labeling_2026_08_11/RESULTS.md`](../../../experiments/perspective_api_labeling_2026_08_11/RESULTS.md) for the expected row counts per day.

## Files allowed to change

- `experiments/perspective_classifiers_2026_08_16/__init__.py`
- `experiments/perspective_classifiers_2026_08_16/README.md`
- `experiments/perspective_classifiers_2026_08_16/consolidate_dataset.py`
- `experiments/perspective_classifiers_2026_08_16/data/dataset.parquet`
- `tests/experiments/perspective_classifiers_2026_08_16/__init__.py`
- `tests/experiments/perspective_classifiers_2026_08_16/test_consolidate_dataset.py`

## Files forbidden to change

- `experiments/perspective_api_labeling_2026_08_11/**` (read only, this is the source of truth for existing labels)
- `feature_generation/perspective_api/**`

## Contract to freeze

`consolidate_dataset.py` exposes one function:

- `build_dataset(label_paths: list[Path]) -> pd.DataFrame`

It reads every path in `label_paths`, keeps only rows where `was_successfully_labeled` is `True`, drops the now-constant `was_successfully_labeled` and `reason` columns, and deduplicates on `uri` keeping the last occurrence (a post can appear in more than one day's file if labeling was rerun). The output keeps these columns: `uri`, `text`, `label_timestamp`, and every `prob_*` / `label_*` pair defined on `PerspectiveApiLabelsModel`.

A `main()` function resolves `label_paths` as every `*.parquet` file under `experiments/perspective_api_labeling_2026_08_11/labels/` (excluding the `tmp/` subdirectory), calls `build_dataset`, and writes the result to `experiments/perspective_classifiers_2026_08_16/data/dataset.parquet`.

## Implementation order

1. Run `git lfs pull` from the repo root so the existing label Parquet files are real data, not LFS pointers.
2. Create the `experiments/perspective_classifiers_2026_08_16/` package with `__init__.py`.
3. Write `build_dataset()` in `consolidate_dataset.py`, following the dedupe pattern already used in `consolidate_labels.py`.
4. Write `main()` to glob the real label files and write `data/dataset.parquet`.
5. Write `test_consolidate_dataset.py` against two small synthetic Parquet fixtures written to `tmp_path` in the test itself (not the real 23 MB label files), covering: a failed row is dropped, a duplicate `uri` keeps the later row, and the output has no `was_successfully_labeled` or `reason` column.
6. Run `main()` for real and record the resulting row count in `README.md`.

## Pass

- `PYTHONPATH=. uv run pytest tests/experiments/perspective_classifiers_2026_08_16/test_consolidate_dataset.py -q` exits `0`.
- `PYTHONPATH=. uv run python experiments/perspective_classifiers_2026_08_16/consolidate_dataset.py` prints the number of rows written and exits `0`.
- `experiments/perspective_classifiers_2026_08_16/data/dataset.parquet` exists and its row count is close to the `successfully_labeled` totals already reported in `experiments/perspective_api_labeling_2026_08_11/RESULTS.md` (within the expected small drop from deduping repeated `uri` values).

## Fail

- Calling the Perspective API or any other network service from this step.
- Silently dropping rows without the dedupe rule above accounting for the drop.
- Hardcoding the list of label Parquet files instead of globbing the labels directory.

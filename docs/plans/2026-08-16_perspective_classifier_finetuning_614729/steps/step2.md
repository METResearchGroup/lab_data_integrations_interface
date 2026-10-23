# Step 2: Split the dataset per label, then into train and test

## Goal

Turn `data/dataset.parquet` into one `data/<label>/data.parquet`, `data/<label>/train.parquet`, and `data/<label>/test.parquet` per Perspective label, with no label named twice and no duplicated training work for labels that are exact copies of each other.

## Scope

Step 2 only reshapes data already produced in Step 1. It does not train a model and does not add any new Perspective attribute.

## Files to inspect

- [`feature_generation/perspective_api/model.py`](../../../feature_generation/perspective_api/model.py), specifically `attribute_to_labels_map` and the `prob_constructive` / `label_constructive` aliasing at the bottom of `_scores_from_attribute_response`, which is the reason `constructive` and `reasoning` are identical columns today.
- The `mirrorView-task` file at `experiments/predict_keep_remove_2026_07_01/models/modernbert/dataloader.py` (fetch via `gh api repos/METResearchGroup/mirrorView-task/contents/experiments/predict_keep_remove_2026_07_01/models/modernbert/dataloader.py --jq .content | base64 -d`) for the stratified split helper this step's split function is modeled on.

## Files allowed to change

- `experiments/perspective_classifiers_2026_08_16/labels.py`
- `experiments/perspective_classifiers_2026_08_16/split_dataset.py`
- `experiments/perspective_classifiers_2026_08_16/data/<label>/data.parquet` for every label
- `experiments/perspective_classifiers_2026_08_16/data/<label>/train.parquet` for every label
- `experiments/perspective_classifiers_2026_08_16/data/<label>/test.parquet` for every label
- `tests/experiments/perspective_classifiers_2026_08_16/test_labels.py`
- `tests/experiments/perspective_classifiers_2026_08_16/test_split_dataset.py`

## Files forbidden to change

- `experiments/perspective_classifiers_2026_08_16/consolidate_dataset.py`
- `experiments/perspective_classifiers_2026_08_16/data/dataset.parquet`
- `feature_generation/perspective_api/**`

## Contract to freeze

`labels.py` derives its label list from `attribute_to_labels_map` in `feature_generation/perspective_api/model.py`, so the list of labels can never drift out of sync with the Perspective client:

- `TRAINED_LABELS: list[str]`, one entry per `attribute_to_labels_map` value's `label` field with the `label_` prefix stripped (for example `toxic`, `moral_outrage`, `spam`), twenty-one entries in total.
- `LABEL_ALIASES: dict[str, str]`, mapping `constructive` to `reasoning`. A served label name is either in `TRAINED_LABELS` or a key in `LABEL_ALIASES`.
- `all_served_labels() -> list[str]` returns `TRAINED_LABELS` plus the keys of `LABEL_ALIASES`.

`split_dataset.py` exposes:

- `build_label_frame(dataset: pd.DataFrame, label: str) -> pd.DataFrame` returns columns `uri`, `text`, `label` (renamed from `label_<name>`, cast to `int`), dropping rows with an empty `text` or a null label.
- `train_test_split_frame(frame: pd.DataFrame, *, test_fraction: float = 0.2, seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame]` does one stratified split on `label`, matching the two-stage split style already used in `mirrorView-task`'s `dataloader.py` but stopping after one split since this plan only needs train and test.
- `main(labels: list[str] | None = None)` runs both functions for every label in `TRAINED_LABELS` (or the given subset) and writes the three Parquet files per label under `experiments/perspective_classifiers_2026_08_16/data/<label>/`.

## Implementation order

1. Write `labels.py` and its test first, since every later step imports `TRAINED_LABELS` and `LABEL_ALIASES` from it.
2. Write `build_label_frame()` and `train_test_split_frame()` in `split_dataset.py` with unit tests against small synthetic DataFrames, checking: the split ratio is close to `test_fraction`, no `uri` appears in both train and test, and the split is stratified (each split's positive rate is close to the full frame's positive rate).
3. Write `main()` and run it for real against `data/dataset.parquet` from Step 1.
4. Record each label's row count and positive rate in `README.md`, so Step 3's class-weight computation has a known baseline to sanity check against.

## Pass

- `PYTHONPATH=. uv run pytest tests/experiments/perspective_classifiers_2026_08_16/test_labels.py tests/experiments/perspective_classifiers_2026_08_16/test_split_dataset.py -q` exits `0`.
- `PYTHONPATH=. uv run python experiments/perspective_classifiers_2026_08_16/split_dataset.py` writes `data/<label>/data.parquet`, `data/<label>/train.parquet`, and `data/<label>/test.parquet` for all twenty-one entries in `TRAINED_LABELS`, and prints each label's row count.
- `experiments/perspective_classifiers_2026_08_16/data/constructive/` does not exist; `constructive` is only ever a key in `LABEL_ALIASES`.

## Fail

- Training data or a config file for `constructive` as though it were its own label.
- A label name in `split_dataset.py` that is spelled differently from the corresponding entry in `attribute_to_labels_map`.
- Any row where the same `uri` appears in both a label's `train.parquet` and `test.parquet`.

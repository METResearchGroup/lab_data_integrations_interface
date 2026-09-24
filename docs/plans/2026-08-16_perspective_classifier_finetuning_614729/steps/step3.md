# Step 3: Build the shared trainer and train each classifier

## Goal

One trainer class fine-tunes a head-only ModernBERT classifier for any label produced in Step 2, and a thin command line wrapper runs it for a single label at a time.

## Scope

Step 3 adds the training code and a shared config, and runs it locally for development. Running it on SageMaker is Step 5.

## Files to inspect

- The `mirrorView-task` files under `experiments/predict_keep_remove_2026_07_01/models/modernbert/` (`train.py`, `dataloader.py`, `configs/modernbert_base.yaml`, `requirements.txt`, `README.md`), fetched the same way as in Step 2. Step 3's `trainer.py` is a direct adaptation of that `train.py`, refactored from a single hardcoded label into a class any label can reuse.
- [`lib/timestamp_utils.py`](../../../lib/timestamp_utils.py) for `get_current_timestamp()`.
- [`lib/load_env_vars.py`](../../../lib/load_env_vars.py) for `EnvVarsContainer.get_env_var`, used only when `report_to` is `wandb`.
- [`pyproject.toml`](../../../pyproject.toml) for the existing `[project.optional-dependencies]` layout to match when adding the new extra.

## Files allowed to change

- `experiments/perspective_classifiers_2026_08_16/configs/base.yaml`
- `experiments/perspective_classifiers_2026_08_16/class_weights.py`
- `experiments/perspective_classifiers_2026_08_16/trainer.py`
- `experiments/perspective_classifiers_2026_08_16/train.py`
- `experiments/perspective_classifiers_2026_08_16/artifacts/<label>/<timestamp>/**`
- `pyproject.toml` (only the new `modernbert-training` optional dependency group)
- `uv.lock`
- `tests/experiments/perspective_classifiers_2026_08_16/test_class_weights.py`
- `tests/experiments/perspective_classifiers_2026_08_16/test_trainer_config.py`

## Files forbidden to change

- `experiments/perspective_classifiers_2026_08_16/labels.py`
- `experiments/perspective_classifiers_2026_08_16/split_dataset.py`
- Any other `[project.optional-dependencies]` group already in `pyproject.toml`

## Contract to freeze

`class_weights.py` is a pure function with no torch import, so it stays testable without the training extra installed:

- `compute_class_weights(labels: Sequence[int]) -> tuple[float, float]` returns `(weight_for_0, weight_for_1)` using the standard balanced formula `weight_for_c = len(labels) / (2 * count_of_c)`, so a perfectly balanced split returns `(1.0, 1.0)` and the rarer class always gets the larger weight. A label split with no positives or no negatives raises `ValueError` naming the label, since a classifier cannot learn a class it never sees.

`configs/base.yaml` holds the hyperparameters shared by every label, matching `mirrorView-task`'s `modernbert_base.yaml` field names:

```yaml
model_name: answerdotai/ModernBERT-base
max_length: 256
learning_rate: 2.0e-5
num_train_epochs: 6
per_device_train_batch_size: 8
per_device_eval_batch_size: 16
weight_decay: 0.01
freeze_encoder: true
random_state: 42
test_fraction: 0.2
report_to: none
wandb_project: perspective-classifiers-2026-08-16
```

`trainer.py` defines `ClassifierTrainer`:

- `__init__(self, label: str, config: dict, experiment_dir: Path)`. `label` must be in `labels.all_served_labels()`; an alias label resolves to its target label's data before doing anything else, so training an alias is a no-op that raises `ValueError` telling the caller to train the target label instead.
- `run(self, *, limit: int | None = None, num_train_epochs: float | None = None) -> Path` loads `data/<label>/train.parquet` and `data/<label>/test.parquet`, tokenizes both, builds `AutoModelForSequenceClassification` from `config["model_name"]` with `attn_implementation="sdpa"` and the encoder frozen outside the classification head when `config["freeze_encoder"]` is true, computes class weights on the train split with `compute_class_weights`, trains with a weighted-loss `Trainer` subclass for `num_train_epochs` (falling back to `config["num_train_epochs"]`), evaluates on the test split as the `Trainer`'s own eval set, and returns the run directory.
- The run directory is `experiment_dir / "artifacts" / label / timestamp`, and it holds the saved model and tokenizer, `metrics.json` (train and test accuracy, precision, recall, f1, roc_auc, pr_auc), `metadata.json` (config used, class weights, row counts, git-independent timestamp), and `train_predictions.parquet` / `test_predictions.parquet` with columns `uri`, `label`, `predicted_label`, `predicted_probability`.
- When `config["report_to"]` is `wandb`, `run()` calls `EnvVarsContainer.get_env_var("WANDB_API_KEY", required=True)` before importing `wandb`; when it is `none` (the default), no external tracking call happens and metrics only land in `metrics.json`.

`train.py` is the command line entrypoint: `--label` (required), `--config` (default `configs/base.yaml`), `--limit`, `--num-train-epochs`. It loads the YAML config, builds one `ClassifierTrainer`, and calls `run()`.

## Implementation order

1. Write `class_weights.py` and its test first; it has no heavy dependencies and is the one piece of training-adjacent logic worth unit testing directly.
2. Add the `modernbert-training` optional dependency group to `pyproject.toml` (`torch`, `transformers`, `datasets`, `accelerate`, `scikit-learn` if not already a floor high enough, `pyyaml`, `wandb`, `sagemaker`), then run `uv lock` to update `uv.lock`.
3. Write `configs/base.yaml`.
4. Write `ClassifierTrainer`, adapting `mirrorView-task`'s `train.py` body into the class described above.
5. Write `train.py` as a thin CLI over `ClassifierTrainer`.
6. Write `test_trainer_config.py` covering only what does not need torch: YAML loads into the expected keys, and an alias label passed to `ClassifierTrainer.__init__` raises `ValueError` before any data loads.
7. Run one real local training pass with `--limit 64 --num-train-epochs 1` for the `moral_outrage` label as a smoke check that the whole path works end to end; keep the deeper multi-label smoke run for Step 6.

## Pass

- `PYTHONPATH=. uv run pytest tests/experiments/perspective_classifiers_2026_08_16/test_class_weights.py tests/experiments/perspective_classifiers_2026_08_16/test_trainer_config.py -q` exits `0` without the `modernbert-training` extra installed.
- `PYTHONPATH=. uv run --extra modernbert-training python experiments/perspective_classifiers_2026_08_16/train.py --label moral_outrage --limit 64 --num-train-epochs 1` exits `0` and prints a run directory under `experiments/perspective_classifiers_2026_08_16/artifacts/moral_outrage/`.
- The printed run directory contains `metrics.json`, `metadata.json`, `train_predictions.parquet`, and `test_predictions.parquet`.

## Fail

- `ClassifierTrainer` accepting `constructive` (or any other alias) as a label to train directly.
- Any hardcoded reference to a specific label name inside `trainer.py` itself; label-specific behavior only comes from `data/<label>/` and the shared config.
- A class-weight computation that silently returns `(1.0, 1.0)` when a label split has zero positives, instead of raising.

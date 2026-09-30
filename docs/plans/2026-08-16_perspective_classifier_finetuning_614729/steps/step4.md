# Step 4: Add the registry and the FastAPI service

## Goal

Callers can send text and a list of desired labels to one HTTP endpoint and get back a prediction from the first label in that list, the same way they already send text to the Perspective API and get back a score.

## Scope

Step 4 adds the registry, a shared prediction helper used by both the API and any command line use, and the FastAPI app itself. It does not change how a label gets trained.

## Files to inspect

- [`backend/main.py`](../../../backend/main.py) for this repo's plain `FastAPI()` style: a module-level `app`, a `/health` route, no framework beyond FastAPI itself.
- The `mirrorView-task` file `experiments/predict_keep_remove_2026_07_01/models/modernbert/predict.py`, fetched the same way as in Step 2, for the single-text inference pattern this step's `predict.py` adapts.
- [`data_platform/generate_features/registry.py`](../../../data_platform/generate_features/registry.py) for this repo's existing plain-dictionary registry pattern.

## Files allowed to change

- `experiments/perspective_classifiers_2026_08_16/predict.py`
- `experiments/perspective_classifiers_2026_08_16/registry.py`
- `experiments/perspective_classifiers_2026_08_16/serving/__init__.py`
- `experiments/perspective_classifiers_2026_08_16/serving/app.py`
- `tests/experiments/perspective_classifiers_2026_08_16/test_registry.py`
- `tests/experiments/perspective_classifiers_2026_08_16/test_app.py`

## Files forbidden to change

- `experiments/perspective_classifiers_2026_08_16/trainer.py`
- `backend/**`

## Contract to freeze

`predict.py` exposes the one function both the CLI and the FastAPI app import, so tokenizing and loading a model happens in exactly one place:

- `predict_proba(text: str, run_dir: Path, *, max_length: int = 256) -> float`, cached per `run_dir` with `functools.lru_cache` so repeated calls for the same label do not reload the model from disk.
- A `__main__` block keeps the existing single-text CLI shape from `mirrorView-task`'s `predict.py`: `--run-dir`, `--text`, `--threshold`, `--max-length`.

`registry.py` exposes:

- `MODEL_REGISTRY: dict[str, Path]`, a plain dictionary from every name in `labels.all_served_labels()` to a run directory under `experiments/perspective_classifiers_2026_08_16/artifacts/`. Someone updates that mapping by hand each time a trained run is promoted to serving; the registry does not scan the filesystem for the newest run.
- `resolve_run_dir(name: str) -> Path` looks up `MODEL_REGISTRY` and raises `KeyError` with a message listing the known names when `name` is not registered.

`serving/app.py` exposes one `FastAPI` app:

- `POST /classify` takes a JSON body `{"text": str, "models": list[str]}`. It uses `models[0]` only. An empty `models` list or an unknown name returns HTTP 404 with the same message `resolve_run_dir` raises. A successful call returns `{"model": str, "label": int, "probability": float}`, where `label` is `1` when `probability >= 0.5`.
- `GET /health` returns `{"status": "ok"}`, matching `backend/main.py`.
- No other routes. Multi-label scoring in one call is intentionally out of scope until there is a real caller that needs it.

## Implementation order

1. Write `predict.py` first, adapted from `mirrorView-task`'s `predict.py`, with the model-loading cache.
2. Write `registry.py` with an empty `MODEL_REGISTRY` to start; it gets real entries once Step 6's smoke run produces real artifacts.
3. Write `test_registry.py` against a registry populated with fake paths in the test itself, covering the unknown-name error and the alias-to-target lookup.
4. Write `serving/app.py`.
5. Write `test_app.py` using FastAPI's `TestClient`, with `predict.predict_proba` monkeypatched to a fixed value so the test does not load a real model. Cover: `models[0]` wins when more than one name is sent, an empty `models` list returns 404, an unknown name returns 404, and `/health` returns `{"status": "ok"}`.

## Pass

- `PYTHONPATH=. uv run pytest tests/experiments/perspective_classifiers_2026_08_16/test_registry.py tests/experiments/perspective_classifiers_2026_08_16/test_app.py -q` exits `0`.
- `PYTHONPATH=. uv run uvicorn experiments.perspective_classifiers_2026_08_16.serving.app:app --port 8090` starts without error, and `curl localhost:8090/health` returns `{"status":"ok"}`.

## Fail

- `serving/app.py` importing `torch` or `transformers` directly instead of going through `predict.py`.
- The endpoint scoring every name in `models` instead of only the first.
- A registry that reads the filesystem to guess the newest run directory instead of using the frozen `MODEL_REGISTRY` mapping.

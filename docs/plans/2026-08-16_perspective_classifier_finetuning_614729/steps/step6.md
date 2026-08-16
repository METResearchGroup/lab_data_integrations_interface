# Step 6: Smoke test end to end

## Goal

Confirm the whole path works on real data for more than one label: train, promote to the registry, serve, and get back a sensible prediction over HTTP.

## Scope

Step 6 only runs existing code from Steps 1 through 4 and records the result. It does not add new production code beyond the registry entries and the results write-up.

## Files to inspect

- `experiments/perspective_classifiers_2026_08_16/train.py`
- `experiments/perspective_classifiers_2026_08_16/registry.py`
- `experiments/perspective_classifiers_2026_08_16/serving/app.py`

## Files allowed to change

- `experiments/perspective_classifiers_2026_08_16/registry.py` (filling in real `MODEL_REGISTRY` entries)
- `experiments/perspective_classifiers_2026_08_16/README.md`
- `experiments/perspective_classifiers_2026_08_16/RESULTS.md`

## Files forbidden to change

- Every other file added in Steps 1 through 5

## Implementation order

1. Train two labels with different positive rates so the smoke test exercises `compute_class_weights` on more than one distribution, for example `moral_outrage` and `spam`, each with `--limit 2000` and a real (not `1`) epoch count.
2. Add both run directories to `MODEL_REGISTRY` in `registry.py`.
3. Start the FastAPI app locally.
4. Send one request per label with a clearly positive example and one with a clearly negative example, and one request listing both labels in `models` to confirm only the first is used.
5. Write the row counts, class weights used, test-set metrics from each label's `metrics.json`, and the four example requests and responses above into `RESULTS.md`.

## Pass

- `PYTHONPATH=. uv run --extra modernbert-training python experiments/perspective_classifiers_2026_08_16/train.py --label moral_outrage --limit 2000` and the same command with `--label spam` each exit `0` and print a run directory.
- `PYTHONPATH=. uv run uvicorn experiments.perspective_classifiers_2026_08_16.serving.app:app --port 8090` stays up.
- `curl -X POST localhost:8090/classify -H 'content-type: application/json' -d '{"text": "example", "models": ["moral_outrage", "spam"]}'` returns a JSON body with `"model": "moral_outrage"`.
- Both labels' test-set `f1` in `metrics.json` are above `0.0` and the response is not the same for an obviously positive example and an obviously negative example.

## Fail

- Treating a `--limit`-truncated smoke run's metrics as a final result worth optimizing against; this step only proves the path works, not that any label's model is production quality.
- Leaving `MODEL_REGISTRY` empty after this step, since Step 4's automated tests use fakes and this is the only step that proves a real registry entry resolves to a real, loadable model.

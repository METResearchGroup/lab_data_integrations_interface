# LLM upscaling experiment (2026-05-18)

## Summary

This experiment evaluates how many posts to request per LLM call when scaling the upsampling pipeline to handle large batches (up to 1,000 posts). The motivating question from [issue #15](https://github.com/METResearchGroup/lab_data_integrations_interface/issues/15) was whether a single call can reliably produce 10, 25, 50, or 100 posts without sacrificing generation quality or diversity.

The experiment sweeps `n_per_call` ∈ {1, 10, 25, 50, 100} while generating 100 posts total from 5 example posts (`experimentation/posts.csv`), using LangChain's `batch()` with `max_concurrency=10`. Diversity is measured via TF-IDF–based metrics: mean pairwise cosine similarity among generated posts (lower = more diverse) and mean cosine similarity to the example posts (how closely outputs track the seed set).

**Key findings:**

- **1 post per LLM call produces the least diverse outputs** — mean pairwise cosine similarity is highest (0.1187), indicating generated posts are more redundant with each other.
- **25–50 posts per call yield the best diversity** — pairwise similarity drops to ~0.065 (n=25) and ~0.059 (n=50), the lowest across all conditions.
- **Similarity to example posts is relatively stable** across conditions (~0.064–0.081), so increasing batch size does not cause outputs to drift further from the seed examples.
- Based on these results, **25 posts per call was chosen as the production default** (configurable via `--n-per-call` on the upsampler CLI), balancing diversity against fewer LLM round-trips.

The implementation landed in [PR #26](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/26), which added parallelized batch upsampling, retry logic, and production metrics to `collector/`.

## Results

Experiment run: 2026-05-18. Target: 100 generated posts per condition, 5 example posts, OpenAI model via LangChain (`DEFAULT_MODEL` from `collector.constants`).

| N (posts/call) | LLM calls | Posts saved | Mean Gini | Mean pairwise cosine sim ↓ | Mean cosine sim to examples |
|----------------|-----------|-------------|-----------|----------------------------|-----------------------------|
| 1              | 100       | 100         | 0.9625    | 0.1187                     | 0.0641                      |
| 10             | 10        | 90          | 0.9636    | 0.0742                     | 0.0794                      |
| 25             | 4         | 96          | 0.9685    | 0.0652                     | 0.0807                      |
| 50             | 2         | 115         | 0.9732    | 0.0585                     | 0.0723                      |
| 100            | 1         | 55          | 0.9631    | 0.0634                     | 0.0729                      |

**Metric definitions:**

- **Mean Gini** — average Gini coefficient of per-post TF-IDF weight vectors; higher values indicate more concentrated (less evenly distributed) term usage.
- **Mean pairwise cosine sim** — average cosine similarity between all pairs of generated posts; **lower is more diverse**.
- **Mean cosine sim to examples** — average similarity of each generated post to the 5 seed example posts.

Note: saved post counts can differ from the target when the LLM returns fewer or more posts than requested in a batch.

## How to Run

From the repo root. Requires a valid OpenAI API key in `.env` (loaded via `python-dotenv`).

**Re-run the experiment** (sweeps all `N_VALUES`, writes CSVs under `results/`, prints the summary table):

```bash
PYTHONPATH=. uv run python experiments/llm_upscaling_2026_05_18/run_experiment.py
```

**Run the production upsampler CLI** (implemented from this experiment; supports up to 1,000 posts):

```bash
PYTHONPATH=. uv run python collector/upsampler.py \
  --examples-path experimentation/posts.csv \
  --num-examples 10 \
  --total-samples 1000 \
  --n-per-call 25
```

`--total-samples` must be divisible by `--n-per-call`.

**Verify the implementation** (from PR #26):

```bash
PYTHONPATH=. uv run python collector/examples_test.py
PYTHONPATH=. uv run pytest tests/collector/test_upsampler.py
```

## Files

| File | Description |
|------|-------------|
| `run_experiment.py` | Main experiment script. Loads 5 example posts, sweeps `n_per_call` over `N_VALUES`, generates posts via LangChain `batch()`, saves outputs, and computes TF-IDF diversity metrics. Prints a Rich summary table. |
| `results/n1/posts.csv` | Generated posts when requesting 1 post per LLM call (100 calls). Column: `text`. |
| `results/n10/posts.csv` | Generated posts when requesting 10 posts per call (10 calls). |
| `results/n25/posts.csv` | Generated posts when requesting 25 posts per call (4 calls). **Chosen production default.** |
| `results/n50/posts.csv` | Generated posts when requesting 50 posts per call (2 calls). |
| `results/n100/posts.csv` | Generated posts when requesting 100 posts per call (1 call). |

Related production code (outside this folder): `collector/upsampler.py`, `collector/metrics.py`, `collector/prompts.py`, `collector/retry.py`.

## References

- [PR #26 — Scale llm upsampling](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/26)
- [Issue #15 — Scale up LLM upsampling to n=1000 samples](https://github.com/METResearchGroup/lab_data_integrations_interface/issues/15)

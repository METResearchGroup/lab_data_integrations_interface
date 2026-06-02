## Remember
- Exact file paths always
- Exact commands with expected output
- DRY, YAGNI, TDD, frequent commits
- Maximum safely delegable parallelism
- Delegated tasks must be impossible to misread

# is_likely_spam feature and curation filter

## Overview
We are adding a new `is_likely_spam` feature to the data platform so feature generation can explicitly identify posts that are likely spam, with a precise policy that only flags clear promotional or clickbait-style content such as posts directing readers to external links for clicks. The same signal will then be wired into curation so spammy records are filtered out of curated outputs, while ordinary opinions, weak takes, and low-value but non-spam text remain eligible.

## Happy Flow
1. A platform post is loaded during feature generation through the existing `data_platform/generate_features/generate_*.py` entrypoints and `FeatureGenerationConfig` in `data_platform/generate_features/generate_features.py`.
2. The new `data_platform/generate_features/is_likely_spam/generate_feature.py` classifies each text record into a boolean or tiered spam label using a narrow prompt that prioritizes explicit spam indicators over generic low quality, opinionated, or annoying content.
3. `data_platform/generate_features/registry.py` registers the new feature so it is generated alongside the existing feature set.
4. `data_platform/curate/consolidate.py` exposes the new feature column in the wide table so rules can reference it, and the platform curation YAML files add a spam exclusion filter.
5. `data_platform/curate/apply_rules.py` continues to evaluate YAML filters sequentially, now including `is_likely_spam == false` or the equivalent rule for each platform’s curate config.
6. `data_platform/curate/curate_*.py` and `data_platform/README.md` document the new feature name and the updated curation behavior so operators know how to generate and filter the dataset end to end.

## Serial Coordination Spine
1. Confirm the exact output shape for `is_likely_spam` so the feature schema, wide-table mapping, and curation rules all agree.
2. Define the spam policy and examples in a new feature module before wiring it into the registry.
3. Update curation contracts and YAML filters after the feature schema is fixed.
4. Add or adjust tests last, after the data model and rule wiring are stable.

## Interface or Contract Freeze
- Feature name: `is_likely_spam`.
- Storage path: `data_platform/data/<platform>/<dataset_id>/features/is_likely_spam.csv`.
- Feature CSV id column: reuse the existing platform binding `feature_csv_id_column` (`uri` today).
- Expected schema: a single explicit spam indicator plus standard metadata fields, matching the platform’s existing feature pattern.
- Curation contract: curated exports must exclude records classified as likely spam, but must not exclude ordinary opinionated, emotional, or low-value text unless the spam feature explicitly marks it true.
- Classification policy: the prompt must distinguish spam from non-spam content and should not over-flag posts merely because they are short, repetitive, promotional-sounding, or low quality unless they clearly try to drive clicks or spammy engagement.

## Parallel Task Packets

### Task P1
- Task ID: `P1`
- Objective: Add the new `is_likely_spam` feature module and register it in the generation registry.
- Why parallelizable: This work is isolated to feature-generation code and does not require curation changes to be complete first.
- Exact files to inspect:
  - `data_platform/generate_features/is_news_or_opinion/generate_feature.py`
  - `data_platform/generate_features/is_political/generate_feature.py`
  - `data_platform/generate_features/is_self_contained/generate_feature.py`
  - `data_platform/generate_features/registry.py`
  - `data_platform/generate_features/models.py`
- Exact files allowed to change:
  - `data_platform/generate_features/is_likely_spam/generate_feature.py`
  - `data_platform/generate_features/registry.py`
  - `data_platform/generate_features/generate_bluesky_features.py`
  - `data_platform/generate_features/generate_twitter_features.py`
  - `data_platform/generate_features/generate_reddit_features.py`
- Exact files forbidden to change:
  - `data_platform/curate/apply_rules.py`
  - `data_platform/curate/consolidate.py`
  - `data_platform/curate/configs/**`
- Preconditions:
  - The existing feature module pattern is confirmed.
  - The output schema choice is frozen by the spine.
- Dependency tasks:
  - Depends on Serial Coordination Spine step 1 and 2 only.
- Required contracts and invariants:
  - `generate_feature(uri, text)` must return a model with the same metadata fields as other LLM features.
  - The prompt must be conservative: false negatives are preferable to over-filtering legitimate opinion content.
- Step-by-step implementation instructions:
  - Create a new package directory `data_platform/generate_features/is_likely_spam/`.
  - Add `generate_feature.py` modeled on the existing single-label LLM features, with a spam-specific system prompt and a structured output schema.
  - Ensure the model includes the explicit output field name selected by the spine.
  - Register the feature in `data_platform/generate_features/registry.py`.
  - Confirm the platform CLIs pick it up via the registry without additional behavior changes unless they currently hard-code feature names.
- Exact verification commands:
  - `PYTHONPATH=. uv run pytest data_platform/generate_features -q`
  - `PYTHONPATH=. uv run python data_platform/generate_features/is_likely_spam/generate_feature.py`
- Expected outputs from verification:
  - Pytest exits `0`.
  - The sample CLI invocation prints a serialized model with the new feature field and no traceback.
- Done-when checklist:
  - New feature module exists.
  - Registry imports succeed.
  - Feature generation CLI sees the new feature.
  - Module-level sample execution works.
- Coordinator review checklist:
  - Prompt is narrow enough to avoid flagging mere opinions or generic low-value text.
  - File names, package names, and registry keys are consistent.
  - No curation files were touched.

### Task P2
- Task ID: `P2`
- Objective: Expose `is_likely_spam` in the wide-table join and add curation filters that exclude likely spam records.
- Why parallelizable: This work only depends on the finalized feature schema and can proceed independently from feature implementation details once the column name is fixed.
- Exact files to inspect:
  - `data_platform/curate/consolidate.py`
  - `data_platform/curate/apply_rules.py`
  - `data_platform/curate/configs/bluesky/mirrorview.yaml`
  - `data_platform/curate/configs/twitter/mirrorview.yaml`
  - `data_platform/curate/configs/reddit/mirrorview.yaml`
  - `data_platform/README.md`
- Exact files allowed to change:
  - `data_platform/curate/consolidate.py`
  - `data_platform/curate/configs/bluesky/mirrorview.yaml`
  - `data_platform/curate/configs/twitter/mirrorview.yaml`
  - `data_platform/curate/configs/reddit/mirrorview.yaml`
  - `data_platform/README.md`
- Exact files forbidden to change:
  - `data_platform/generate_features/is_likely_spam/generate_feature.py`
  - `data_platform/generate_features/registry.py`
  - `data_platform/generate_features/generate_*.py`
- Preconditions:
  - The feature schema name is frozen.
  - The new feature CSV exists or will exist once generation runs.
- Dependency tasks:
  - Depends on Serial Coordination Spine step 1.
- Required contracts and invariants:
  - The new wide-table column must use a stable, descriptive alias such as `is_likely_spam`.
  - Curation rules must exclude `true` spam labels and keep `false` labels.
  - Existing filters must retain their current meaning unless the spam rule is the only change.
- Step-by-step implementation instructions:
  - Add `is_likely_spam` to `FEATURE_WIDE_COLUMNS` in `data_platform/curate/consolidate.py`.
  - Update each mirrorview curation YAML to include a final spam-exclusion filter.
  - Update `data_platform/README.md` to document the new feature column and the curation exclusion rule.
  - Preserve existing filter order unless a later rule depends on the spam column being applied earlier.
- Exact verification commands:
  - `PYTHONPATH=. uv run pytest data_platform/curate -q`
  - `PYTHONPATH=. uv run python data_platform/curate/curate_bluesky.py --dataset-id <existing_dataset_id> --config mirrorview.yaml`
  - `PYTHONPATH=. uv run python data_platform/curate/curate_twitter.py --dataset-id <existing_dataset_id> --config mirrorview.yaml`
  - `PYTHONPATH=. uv run python data_platform/curate/curate_reddit.py --dataset-id <existing_dataset_id> --config mirrorview.yaml`
- Expected outputs from verification:
  - Pytest exits `0`.
  - Each curation command produces a curated output path without missing-column errors.
  - The resulting curated table excludes rows where `is_likely_spam` is `true`.
- Done-when checklist:
  - Wide-table SQL includes the spam column.
  - Each platform curation config filters spam out.
  - README reflects the new contract.
- Coordinator review checklist:
  - The filter uses the exact bool semantics intended by `apply_rules.py`.
  - No unrelated curation rules changed.
  - Column alias is consistent across docs and YAML.

## Integration Order
1. Merge `P1` feature generation first so the new CSV can be produced.
2. Merge `P2` curation wiring second so curated outputs can consume the new feature.
3. Run cross-cutting smoke tests after both tasks land to confirm feature generation and curation remain in sync.

## Final Verification
- `PYTHONPATH=. uv run pytest data_platform -q`
- `PYTHONPATH=. uv run python data_platform/generate_features/generate_bluesky_features.py --dataset-id <existing_dataset_id> --batch-size 64 --no-opik --features is_likely_spam`
- `PYTHONPATH=. uv run python data_platform/curate/curate_bluesky.py --dataset-id <existing_dataset_id> --config mirrorview.yaml`
- `PYTHONPATH=. uv run python data_platform/generate_features/generate_twitter_features.py --dataset-id <existing_dataset_id> --batch-size 64 --no-opik --features is_likely_spam`
- `PYTHONPATH=. uv run python data_platform/curate/curate_twitter.py --dataset-id <existing_dataset_id> --config mirrorview.yaml`
- `PYTHONPATH=. uv run python data_platform/curate/curate_reddit.py --dataset-id <existing_dataset_id> --config mirrorview.yaml`

## Alternative approaches
We could implement spam filtering as a separate post-processing heuristic outside the feature registry, but that would fragment the contract and make curation harder to reason about. Using a first-class feature keeps generation, labeling, and downstream filtering aligned, and it reuses the existing resumable feature pipeline rather than introducing a one-off path.

## Notes
- The plan intentionally keeps the spam policy conservative so that opinionated or low-value posts are not filtered unless the classifier sees explicit spam behavior.
- If the exact schema should be boolean-only versus a multi-class tiered model, that decision should be finalized in the serial coordination spine before implementation begins.

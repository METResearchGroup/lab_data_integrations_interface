## Remember
- Exact file paths always
- Exact commands with expected output
- DRY, YAGNI, TDD, frequent commits
- Maximum safely delegable parallelism
- Delegated tasks must be impossible to misread

## Overview
We will make Opik disabled by default for platform feature generation so large batch jobs no longer require `--no-opik` to avoid telemetry overhead. The change should preserve the existing explicit opt-in path for anyone who still wants Opik enabled, while updating CLIs, defaults, tests, and docs so the default behavior is unambiguous and stable across Bluesky, Twitter, and Reddit feature generation.

## Happy Flow
1. A user runs one of the feature-generation entrypoints in [`data_platform/generate_features/generate_bluesky_features.py`](data_platform/generate_features/generate_bluesky_features.py), [`data_platform/generate_features/generate_twitter_features.py`](data_platform/generate_features/generate_twitter_features.py), or [`data_platform/generate_features/generate_reddit_features.py`](data_platform/generate_features/generate_reddit_features.py) without passing `--no-opik`.
2. The CLI constructs `FeatureRunConfig` in the platform-specific `generate_*_features(...)` function with Opik disabled by default, while still allowing an explicit flag or override to turn it on.
3. The run config flows into [`data_platform/generate_features/models.py`](data_platform/generate_features/models.py) and then through [`data_platform/generate_features/generate_features.py`](data_platform/generate_features/generate_features.py), where `opik_telemetry.set_opik_enabled(...)` and the conditional `flush()` respect the new default.
4. Metadata written to `features/metadata.json` continues to record the runtime setting so resumed runs keep the same telemetry behavior as the original run.
5. Existing tests in [`tests/data_platform/generate_features/`](tests/data_platform/generate_features/) and [`tests/ml_tooling/test_opik_disabled.py`](tests/ml_tooling/test_opik_disabled.py) validate the new default, explicit override behavior, and round-trip metadata serialization.
6. Documentation in [`data_platform/README.md`](data_platform/README.md) and the module docstrings in the three CLI files stop advertising `--no-opik` as the normal invocation path.

## Serial Coordination Spine
1. Confirm the current defaulting behavior in [`data_platform/generate_features/models.py`](data_platform/generate_features/models.py), the three platform CLI modules, and [`data_platform/generate_features/generate_features.py`](data_platform/generate_features/generate_features.py).
2. Define the interface decision: Opik is off by default for feature generation, but an explicit `--opik` or equivalent override remains available if the repo already has a supported enable path; if not, preserve only the programmatic override path and keep CLI defaults disabled.
3. Update the shared config/default path first, then the platform-specific CLI entrypoints, so the runtime semantics and help text stay aligned.
4. Update docs and tests only after the behavioral contract is fixed.

## Interface or Contract Freeze
- `FeatureRunConfig.opik_enabled` in [`data_platform/generate_features/models.py`](data_platform/generate_features/models.py) becomes the authoritative default for new feature-generation runs.
- The platform `generate_*_features(...)` helpers in [`data_platform/generate_features/generate_bluesky_features.py`](data_platform/generate_features/generate_bluesky_features.py), [`data_platform/generate_features/generate_twitter_features.py`](data_platform/generate_features/generate_twitter_features.py), and [`data_platform/generate_features/generate_reddit_features.py`](data_platform/generate_features/generate_reddit_features.py) must construct a run config that disables Opik unless the caller explicitly opts in.
- [`data_platform/generate_features/generate_features.py`](data_platform/generate_features/generate_features.py) must continue to honor `config.run_config.opik_enabled` for trace setup and flush behavior, with no change to the resume logic or batch labeling semantics.
- [`data_platform/generate_features/metadata.py`](data_platform/generate_features/metadata.py) must continue to round-trip the `config.opik_enabled` field so old metadata and new metadata both load safely.

## Parallel Task Packets

### P1: Shared default contract
- **Task ID:** P1
- **Objective:** Change the shared feature-generation default so Opik is disabled unless explicitly enabled.
- **Why parallelizable:** This task touches only the shared run-config contract and metadata round-trip, and can be completed independently of CLI text edits.
- **Files to inspect:** [`data_platform/generate_features/models.py`](data_platform/generate_features/models.py), [`data_platform/generate_features/generate_features.py`](data_platform/generate_features/generate_features.py), [`tests/data_platform/generate_features/test_metadata.py`](tests/data_platform/generate_features/test_metadata.py), [`tests/data_platform/generate_features/test_generate_features.py`](tests/data_platform/generate_features/test_generate_features.py), [`tests/ml_tooling/test_opik_disabled.py`](tests/ml_tooling/test_opik_disabled.py)
- **Files allowed to change:** [`data_platform/generate_features/models.py`](data_platform/generate_features/models.py), [`tests/data_platform/generate_features/test_metadata.py`](tests/data_platform/generate_features/test_metadata.py), [`tests/data_platform/generate_features/test_generate_features.py`](tests/data_platform/generate_features/test_generate_features.py), [`tests/ml_tooling/test_opik_disabled.py`](tests/ml_tooling/test_opik_disabled.py)
- **Files forbidden to change:** The three CLI files, [`data_platform/README.md`](data_platform/README.md), and any engine implementation files under [`data_platform/generate_features/engines/`](data_platform/generate_features/engines/)
- **Preconditions:** None beyond repo checkout and a readable test environment.
- **Dependency tasks:** None.
- **Required contracts and invariants:** New `FeatureRunConfig()` instances should default to `opik_enabled=False`; loading existing metadata that omits the field must still work; explicit `opik_enabled=True` must still enable telemetry.
- **Step-by-step implementation instructions:**
  1. Update the `FeatureRunConfig` dataclass default in [`data_platform/generate_features/models.py`](data_platform/generate_features/models.py) from `True` to `False`.
  2. Audit [`data_platform/generate_features/generate_features.py`](data_platform/generate_features/generate_features.py) for any assumptions that rely on the old default and keep the runtime branching intact.
  3. Extend or adjust tests so the default config path asserts disabled Opik, while explicit `FeatureRunConfig(opik_enabled=True)` still exercises the enabled path.
  4. Ensure metadata serialization/deserialization still round-trips `opik_enabled` with the new default.
- **Exact verification commands:**
  - `PYTHONPATH=. uv run pytest tests/data_platform/generate_features/test_metadata.py tests/data_platform/generate_features/test_generate_features.py tests/ml_tooling/test_opik_disabled.py -q`
- **Expected outputs from verification:** All targeted tests pass; no regressions in metadata loading or trace-disable behavior.
- **Done-when checklist:**
  - `FeatureRunConfig()` now means Opik off.
  - A metadata file missing `opik_enabled` still loads as disabled.
  - Tests prove the enabled override still works.
- **Coordinator review checklist:**
  - Default flip is limited to the shared config contract.
  - No resume/batch semantics changed.
  - No unrelated refactors introduced.

### P2: Bluesky CLI default
- **Task ID:** P2
- **Objective:** Make Bluesky feature generation default to Opik off and keep the CLI help/docstring accurate.
- **Why parallelizable:** This task only touches the Bluesky entrypoint and its tests/docs.
- **Files to inspect:** [`data_platform/generate_features/generate_bluesky_features.py`](data_platform/generate_features/generate_bluesky_features.py), [`tests/data_platform/generate_features/test_generate_features.py`](tests/data_platform/generate_features/test_generate_features.py), [`data_platform/README.md`](data_platform/README.md)
- **Files allowed to change:** [`data_platform/generate_features/generate_bluesky_features.py`](data_platform/generate_features/generate_bluesky_features.py), [`data_platform/README.md`](data_platform/README.md), [`tests/data_platform/generate_features/test_generate_features.py`](tests/data_platform/generate_features/test_generate_features.py)
- **Files forbidden to change:** The shared `FeatureRunConfig` model file and Twitter/Reddit CLI files.
- **Preconditions:** P1 is either complete or its contract is clearly defined so this task can target the same default without ambiguity.
- **Dependency tasks:** P1.
- **Required contracts and invariants:** `generate_bluesky_features(...)` should default to disabled Opik with no new side effects on batch sizing, dataset validation, or feature subset handling.
- **Step-by-step implementation instructions:**
  1. Update the Bluesky docstring in [`data_platform/generate_features/generate_bluesky_features.py`](data_platform/generate_features/generate_bluesky_features.py) to remove `--no-opik` from the default usage example.
  2. Change the CLI signature so the default invocation does not require `--no-opik` for the desired behavior.
  3. If the codebase keeps an explicit enable flag, make it the opt-in path and ensure the generated `FeatureRunConfig` still receives the correct boolean.
  4. Update [`data_platform/README.md`](data_platform/README.md) command examples to match the new default.
  5. Adjust or add a Bluesky feature-generation test in [`tests/data_platform/generate_features/test_generate_features.py`](tests/data_platform/generate_features/test_generate_features.py) if it covers the Bluesky helper path.
- **Exact verification commands:**
  - `PYTHONPATH=. uv run pytest tests/data_platform/generate_features/test_generate_features.py -q`
  - `PYTHONPATH=. uv run python data_platform/generate_features/generate_bluesky_features.py --help`
- **Expected outputs from verification:** The helper test passes, and CLI help/examples no longer imply `--no-opik` is the standard invocation.
- **Done-when checklist:**
  - Bluesky default path disables Opik.
  - Documentation example is updated.
  - Help text matches the new default.
- **Coordinator review checklist:**
  - CLI behavior matches the shared default.
  - No Bluesky-only regression in dataset loading or feature subset handling.

### P3: Twitter and Reddit CLI defaults
- **Task ID:** P3
- **Objective:** Make Twitter and Reddit feature generation default to Opik off and update their docs/examples.
- **Why parallelizable:** This task is isolated to the two remaining platform CLIs and their documentation.
- **Files to inspect:** [`data_platform/generate_features/generate_twitter_features.py`](data_platform/generate_features/generate_twitter_features.py), [`data_platform/generate_features/generate_reddit_features.py`](data_platform/generate_features/generate_reddit_features.py), [`data_platform/README.md`](data_platform/README.md), [`tests/data_platform/generate_features/test_generate_twitter_features.py`](tests/data_platform/generate_features/test_generate_twitter_features.py), [`tests/data_platform/generate_features/test_generate_reddit_features.py`](tests/data_platform/generate_features/test_generate_reddit_features.py)
- **Files allowed to change:** [`data_platform/generate_features/generate_twitter_features.py`](data_platform/generate_features/generate_twitter_features.py), [`data_platform/generate_features/generate_reddit_features.py`](data_platform/generate_features/generate_reddit_features.py), [`data_platform/README.md`](data_platform/README.md), [`tests/data_platform/generate_features/test_generate_twitter_features.py`](tests/data_platform/generate_features/test_generate_twitter_features.py), [`tests/data_platform/generate_features/test_generate_reddit_features.py`](tests/data_platform/generate_features/test_generate_reddit_features.py)
- **Files forbidden to change:** [`data_platform/generate_features/models.py`](data_platform/generate_features/models.py) and [`data_platform/generate_features/generate_features.py`](data_platform/generate_features/generate_features.py)
- **Preconditions:** P1 contract is established.
- **Dependency tasks:** P1.
- **Required contracts and invariants:** Both helpers must default to disabled Opik, preserve `--features`, `--batch-size`, and `--max-concurrency`, and not alter path validation or dataset ID semantics.
- **Step-by-step implementation instructions:**
  1. Update the Twitter and Reddit module docstrings so the example commands no longer present `--no-opik` as a required or standard flag.
  2. Flip the CLI defaults or rename the option if needed so default runs disable Opik.
  3. Update the corresponding test modules to assert the new default contract for each platform helper.
  4. Refresh the feature-generation sections of [`data_platform/README.md`](data_platform/README.md) so all platform examples reflect the new default.
- **Exact verification commands:**
  - `PYTHONPATH=. uv run pytest tests/data_platform/generate_features/test_generate_twitter_features.py tests/data_platform/generate_features/test_generate_reddit_features.py -q`
  - `PYTHONPATH=. uv run python data_platform/generate_features/generate_twitter_features.py --help`
  - `PYTHONPATH=. uv run python data_platform/generate_features/generate_reddit_features.py --help`
- **Expected outputs from verification:** The platform tests pass, and both CLI help outputs align with the disabled-by-default behavior.
- **Done-when checklist:**
  - Twitter default path disables Opik.
  - Reddit default path disables Opik.
  - README examples are consistent across platforms.
- **Coordinator review checklist:**
  - No divergence between platforms.
  - No accidental change to CLI argument names or dataset handling.

## Integration Order
1. Merge P1 first so the shared default and metadata semantics are stable.
2. Merge P2 next so Bluesky behavior is aligned with the new contract and docs.
3. Merge P3 last so Twitter and Reddit match the same default and the README is consistent end-to-end.
4. After all packets land, run the full feature-generation test slice plus direct CLI help checks to confirm the user-facing default is consistent everywhere.

## Final Verification
- `PYTHONPATH=. uv run pytest tests/data_platform/generate_features tests/ml_tooling/test_opik_disabled.py -q`
- `PYTHONPATH=. uv run python data_platform/generate_features/generate_bluesky_features.py --help`
- `PYTHONPATH=. uv run python data_platform/generate_features/generate_twitter_features.py --help`
- `PYTHONPATH=. uv run python data_platform/generate_features/generate_reddit_features.py --help`
- Confirm the README examples in [`data_platform/README.md`](data_platform/README.md) show the default invocation without `--no-opik`.

## Alternative approaches
- Keep `--no-opik` as the only supported knob and just change internal defaults. We are not choosing this because it preserves the old ergonomics and still nudges users toward an explicit flag for the common case.
- Rename the option to an explicit `--opik` enable flag. This is cleaner semantically, but it is a broader CLI compatibility change; the safer first step is to flip the default while preserving existing invocation patterns where possible.

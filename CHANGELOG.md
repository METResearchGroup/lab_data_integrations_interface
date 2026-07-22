# CHANGELOG

## 2026-07-19

1. Added a short-term Bluesky AOC-followers backfill experiment under `experimentation/aoc_followers_backfill/` (issue #115 / #111): discover 10 qualifying followers of AOC (AppView; >1,000 followers and ≥5 posts in the past week), then backfill each user's posts, likes, reposts, and follows for a configurable window via relay `getRepo` (CAR/MST decode) with CSV + `metadata.json` outputs and timing/date-window scalability experiments. Strategy notes on `getRepo` return types in `strategy_planning/2026-07-15_getrepo_return_type.md`. [PR #119](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/119)

## 2026-07-15

1. Published technical roadmap status updates: `strategy_planning/2026-07-09_technical_roadmap_updates.md` summarizing V1 pipeline/frontend/backend/observability progress and next work (Jetstream/more data types, agentic search), plus `docs/design_docs/2026-07-09_agentic_search_system_design.md` for natural-language / agentic search. Added doctoc pre-commit + `scripts/update_doc_tocs.sh`, refreshed TOCs across strategy docs and the past-post-lookups ADR, and tightened `.gitignore` / Vulture skip config. [PR #114](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/114)

## 2026-07-09

1. Added `README.md` files for five experiment directories under `experiments/` (`database_experiments_2026_05_23`, `dedup_comparison_2026_06_12`, `llm_upscaling_2026_05_18`, `reddit_fetch_data_2026_05_23`, `x_fetch_data_2026_06_01`), documenting motivation, results, how to reproduce, and related PRs/issues. [PR #112](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/112)

## 2026-07-08

1. Added backend observability for the Railway app (issue #102): OpenTelemetry instrumentation dependencies, Railway start command wired for OTel, debug-level logging on `/health`, `.env.example` Grafana Cloud / OTel settings, and runbooks `docs/runbooks/HOW_TO_ADD_OBSERVABILITY_GRAFANA.md` plus `docs/runbooks/HOW_TO_RUN_BACKEND_APP.md`. [PR #110](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/110)

## 2026-07-07

1. Added post-curation local disk cleanup (issue #92): gate check that all stage `metadata.json` files report successful S3 upload, then remove the dataset directory; wired into the Bluesky orchestrator with unit + E2E tests. [PR #108](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/108)

## 2026-07-03

1. Added orchestration-level pipeline run metadata (issue #91): generate a `pipeline_run_id` per Bluesky Prefect invocation, persist stage success/failure records to DynamoDB (Terraform + wrapper), separate from stage lineage in `metadata.json`. See `strategy_planning/2026-06-29_pipeline_run_metadata.md`. [PR #99](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/99)
2. Hotfixed Railway deploy by merging missing `railway.json` into the deploy branch. [PR #103](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/103)
3. Hotfixed Railway builds by removing the explicit Nixpacks builder pin that failed when `NIXPACKS_UV_VERSION` was unset. [PR #104](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/104)
4. Added hotfix deploy runbook `docs/runbooks/HOW_TO_DEPLOY_HOTFIX.md`. [PR #105](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/105)
5. Added Railway preview-build runbook so build failures can be caught before merge to main. [PR #106](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/106)

## 2026-07-02

1. Added Railway deploy config for the FastAPI backend (`railway.json` start command from repo root) and runbook `docs/runbooks/backend-railway-deploy.md` covering AWS/CORS env vars vs data-platform collector secrets. [PR #101](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/101)

## 2026-07-01

1. Added Vercel UI deploy notes in `docs/runbooks/HOW_TO_DEPLOY_UI_TO_VERCEL.md`. [PR #100](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/100)

## 2026-06-30

1. Captured initial design for run-level pipeline metadata in `strategy_planning/2026-06-29_pipeline_run_metadata.md` (orchestration first, then metadata plug-in). [PR #98](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/98)

## 2026-06-27

1. Extended stage-level deduplication beyond ingestion (issues #89 / #90): Athena-backed dedupe for preprocessing and feature generation, Glue partition updates after S3 upload, upstream gate checks that hard-fail if prior stages are incomplete, and same-`dataset_id` run sweeps. Curation intentionally not URI-deduped (multiple curate configs). See `strategy_planning/2026-06-26_pipeline_stage_flows.md`. [PR #97](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/97)

## 2026-06-25

1. Added backend query v1: FastAPI endpoints for recent posts, top authors, and keyword counts over Athena, with Athena helpers and a dedicated S3 results workspace (queries still approximate “today/week” against available dataset partitions). [PR #95](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/95)
2. Wired three example queries into the frontend (“Choose Query”), CORS to the backend, and result display after a backend call. [PR #96](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/96)

## 2026-06-24

1. Set up Glue/Athena external tables for raw, preprocessed, curated, and the seven feature datasets (10 tables total), with partition registration after successful raw S3 upload; switched ingestion Athena ID lookups to the posts table. [PR #94](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/94)

## 2026-06-23

1. Extended S3 sync from ingestion to preprocessing, feature generation, and curation; generalized hardcoded CSV paths to follow `dataset.json` output extension; added parquet-output ingestion YAML variant. [PR #93](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/93)

## 2026-06-22

1. Added S3 sync for curated outputs + metadata and post-URI parquet after ingestion (issues #56 / #89), with local dataset cleanup after upload; always check disk + Athena for dedupe (removed `--resume`). [PR #77](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/77)

## 2026-06-20

1. Added ordered pipeline ticket breakdown in `strategy_planning/2026-06-19_pipeline_tickets.md` (Glue tables → S3 uploads → stage dedupe → metadata uploads → disk cleanup). [PR #85](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/85) [PR #86](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/86)
2. Added data platform progress summary `strategy_planning/2026-06-19_data_platform_progress_summary.md` covering stage behavior, where dedupe does/doesn't apply, and open questions. [PR #87](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/87)

## 2026-06-19

1. Added data platform correctness / design-choice notes under `strategy_planning/` (`2026-06-19_data_pipeline_design_choices.md`, `2026-06-19_data_platform_pipeline_correctness.md`). [PR #78](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/78)

## 2026-06-17

1. Refactored ingestion toward policy-based deduplication (`current_run`, `prior_runs_same_dataset`, `prior_runs_all_datasets` unioned in `dedupe_policy`) and cleaned up AI-generated ingestion slop. [PR #67](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/67)
2. Moved past-run ID checks to Athena + S3 (issue #75): current-run disk IDs plus Athena lookup of historical IDs; added S3/Glue/Athena infra for seen-ID storage and results. [PR #76](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/76)

## 2026-06-16

1. Experimented on already-processed post URI stores (issue #71): DynamoDB vs S3+SQLite vs Athena vs DuckDB latency and scale-degradation measurements under `experiments/`. [PR #72](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/72)

## 2026-06-12

1. Migrated ingestion dedupe to explicit `dedupe_policy` at the storage write boundary (`DedupeSession` / `open_dedupe_session` / `append_deduped_records`), rewriting all ingestion YAMLs and removing the prior boolean-flag helper module. [PR #68](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/68)
2. Bluesky trump/economy/iran batch (~1k posts): parquet-or-CSV `output_format` via `dataset.json`, Prefect `orchestrate_bluesky.py` runs all four stages with config CLI flags, plus runbook. [PR #65](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/65)
3. Added a new Reddit Mirrorview collection run (`reddit_29747ef4-…`) through ingest → preprocess → features → curated. [PR #69](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/69)

## 2026-06-10

1. Added platform-scoped cross-dataset ingestion dedupe (default on via `dedupe_across_datasets`): skip Reddit/Twitter/Bluesky IDs already present under any raw run on that platform. [PR #66](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/66)

## 2026-06-02

1. Scaled Twitter collection with cross-run tweet-ID dedupe (`dedupe_tweets_from_prior_raw_runs`) and `mirrorview_scale.yaml` targeting 10k rows. [PR #50](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/50)
2. Ran Twitter batch collection job 2 (expanded `twitter_a8f3c22d-…` raw/preprocessed/features/curated artifacts). [PR #55](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/55)
3. Disabled Opik by default for platform feature generation; platforms opt in with `--opik`. [PR #58](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/58)
4. Added Vulture (dead code) and Biome (JS lint/format) to CI/pre-commit (issue #13). [PR #52](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/52)
5. Updated Twitter preprocessing to merge all raw runs by default (newest-wins `tweet_id` dedupe), with `--latest-only` and `source_raw_runs` metadata. [PR #63](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/63)
6. Added `is_likely_spam` LLM feature + Mirrorview curation filter (`is_likely_spam == false`) across platforms. [PR #61](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/61)
7. Ran Twitter collection batch 3 (`keyword_politics_econ_7000` / `twitter_3b46b8f9-…`, ~8k records through the pipeline). [PR #64](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/64)

## 2026-06-01

1. Initialized the data platform: Bluesky ingestion CLI with checkpointing/resumable runs, LLM feature classifiers + toxicity scoring, feature registry/orchestration, preprocessing validators, Mirrorview curation, and storage/dataset tests. [PR #35](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/35)
2. Added OpenTelemetry fanout/DB trace topology experiment endpoints (`/fanout`, `/db`) for Tempo inspection (issue #19). [PR #34](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/34)
3. Created the feature generation execution engine (batched LLM labeling with skip-already-labeled URIs). [PR #40](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/40)
4. Synced Reddit through the shared pipeline (ingestion models + feature generation entrypoints). [PR #41](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/41)
5. Tightened Mirrorview curation to require `political_stance in [left, right]` for Reddit and Bluesky. [PR #42](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/42)
6. Migrated Bluesky/Reddit pipeline entrypoints to shared stage runners (`config_paths`, preprocess/feature/curate runners) with thin platform CLIs. [PR #43](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/43)
7. Fixed main CI lint failures from recent merges (ruff/pyright/complexipy). [PR #44](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/44)
8. Added Reddit `mirrorview_scale` ingestion (`listing: top` + `listing_time_filter: month`, higher limits, dedupe comments from prior raw runs). [PR #45](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/45)
9. Added X keyword fetch experiment under `experiments/x_fetch_data_2026_06_01/` (API v2 recent search, 100-post cap). [PR #46](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/46)
10. Added Twitter Mirrorview ingestion pipeline (`sync_twitter.py`, Tweepy recent search, resumable per-keyword checkpoints, 1k-row pilot config). [PR #47](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/47)
11. Added Twitter preprocess / feature / curate CLIs on shared runners (t.co strip + length validators; Mirrorview curate YAML). [PR #48](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/48)
12. Persisted t.co scrubbing into Twitter preprocessed text via a shared `text_transform` hook (plus scrub/verify scripts). [PR #49](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/49)

## Open / in progress

1. Design doc for the Bluesky Backfill App (Jetstream continuous ingestion, cursor tracking, buffered flush to storage, S3/Glue query projection) remains open: `docs/design_docs/2026-07-13_bluesky_backfill_app.md`. [PR #118](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/118)

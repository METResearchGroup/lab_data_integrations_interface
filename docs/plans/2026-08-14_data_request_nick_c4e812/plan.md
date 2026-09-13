# Deliver Nick's 12-month Bluesky extract for the greedy-10 cohort

## Remember
- Exact file paths always
- Exact commands with expected output
- DRY, YAGNI, TDD, frequent commits
- Delegated tasks must be impossible to misread.

## Overview

Turn `experiments/data_request_2026_08_14/greedy10_dedup_members.csv` (8,431 DIDs) into a timestamped CSV bundle covering the fields in `experiments/data_request_2026_08_14/REQUEST_DETAILS.md` over a trailing 12-month window. File and column contracts live in `experiments/data_request_2026_08_14/EXPECTED_FILES.md`. Reuse the getRepo decode path in `experiments/aoc_getrepo_derived_stats_2026_08_11/`. Ship usable CSVs from profiles and cached repos first. Fill `posts.csv` with AppView `getPosts` later, and only for URIs that are still `pending`.

`getPosts` on liked posts is the 1 to 4 day job. It is not required for the first folder. See `experiments/data_request_2026_08_14/RUNTIME_ESTIMATE.md`.

## Happy flow

An operator runs one entrypoint in stages. Profiles can be written without getRepo. Repos are cached per DID and skipped on resume. After repos are on disk, the job writes activity, graph, and `posts.csv` join keys with no AppView post lookup. Later runs pass `--from-dir` and `--hydrate` to fill `posts.csv` without downloading repos again. Saves are an empty schema file. Unfollows are omitted.

```mermaid
flowchart TD
  input["greedy10_dedup_members.csv"] --> profiles["AppView profiles"]
  profiles --> outA["profiles.csv"]
  input --> cache{"Repo cache hit?"}
  cache -->|no| repos["getRepo per DID"]
  cache -->|yes| decode["Decode from cache"]
  repos --> decode
  decode --> window["Keep actor records in 12-month window"]
  window --> events["likes reposts quotes replies originals"]
  window --> graph["follow_edges.csv"]
  events --> posts["posts.csv repo_only and pending"]
  profiles --> outC["Timestamped folder"]
  posts --> outC
  events --> outC
  graph --> outC
  outC --> hydrate["Optional getPosts by hydrate mode"]
  hydrate --> posts
```

Operator commands, from the repo root:

```bash
PYTHONPATH=. uv run python experiments/data_request_2026_08_14/main.py --profiles-only
PYTHONPATH=. uv run python experiments/data_request_2026_08_14/main.py --hydrate none
PYTHONPATH=. uv run python experiments/data_request_2026_08_14/main.py --from-dir experiments/data_request_2026_08_14/data/<timestamp> --hydrate own_posts
PYTHONPATH=. uv run python experiments/data_request_2026_08_14/main.py --from-dir experiments/data_request_2026_08_14/data/<timestamp> --hydrate quotes_replies
PYTHONPATH=. uv run python experiments/data_request_2026_08_14/main.py --from-dir experiments/data_request_2026_08_14/data/<timestamp> --hydrate all
```

## Approach

Keep post text and counts in `posts.csv` once. Activity files store the actor, the event id, timestamps, and post URI join keys. Public repos are the source of what each person did. Cache each decoded repo on disk so a crash does not redo finished DIDs. AppView profiles can ship before repos. AppView `getPosts` is a later fill of `posts.csv`, using one global URI set and skipping rows that are already `ok`. Do not invent private bookmarks or deleted follows.

## Steps

### Step 1: Freeze window, cohort, and output contracts

Lock the 12-month bound, the 8,431-DID input, hydrate modes, and the schemas in `experiments/data_request_2026_08_14/EXPECTED_FILES.md`. Add failing tests that check written CSV headers against that doc. See [steps/step1.md](steps/step1.md).

### Step 2: Profile fields for every DID

Resolve current handle, display name, bio, and follower/followee counts via public AppView profile calls. Account createdAt comes from the getRepo profile record in Step 3. Step 5 can write `profiles.csv` with `--profiles-only`. See [steps/step2.md](steps/step2.md).

### Step 3: getRepo fetch, decode, and resume cache

Download each repo through the existing relay getRepo and decode helpers. Write a per-DID cache and skip DIDs that are already cached. Keep posts, likes, reposts, follows, and the profile record. Record per-DID failures without aborting the cohort. See [steps/step3.md](steps/step3.md).

### Step 4: Activity tables and posts rows from the repo cache

Filter actor records to the window. Write originals, likes, reposts, quotes, and replies. Put member-authored posts and like/repost/quote/reply-parent URIs into `posts.csv` with no AppView lookup. Member posts are `repo_only`. Other URIs are `pending`. Write an empty saves table. See [steps/step4.md](steps/step4.md).

### Step 5: Follows, write the first folder, and smoke

Build current follow edges where both ends are in the cohort. Write follow creates during the window that still exist. Wire `--profiles-only` and `--hydrate none`. Smoke a small DID subset, then the full list can run overnight for getRepo only. See [steps/step5.md](steps/step5.md).

### Step 6: Resumable getPosts into posts.csv

Look up pending URIs on public AppView in modes `own_posts`, `quotes_replies`, and `all`. Skip rows that are already `ok`. Do not call getRepo again. See [steps/step6.md](steps/step6.md).

## What "done" looks like

1. Per-step specs exist under `docs/plans/2026-08-14_data_request_nick_c4e812/steps/`.
2. `experiments/data_request_2026_08_14/EXPECTED_FILES.md` is the schema source of truth.
3. Experiment code lives under `experiments/data_request_2026_08_14/` and imports decode helpers from `experiments/aoc_getrepo_derived_stats_2026_08_11/` and `experimentation/aoc_followers_backfill/` rather than copying decode code.
4. `--profiles-only` writes `profiles.csv` without getRepo.
5. getRepo writes `experiments/data_request_2026_08_14/cache/repos/` per DID and resumes by skipping cache hits.
6. `--hydrate none` writes every generated file named in `EXPECTED_FILES.md`. Member posts in `posts.csv` are `repo_only`. Like, repost, quote, and parent URIs are `pending`. Activity tables join on those URIs.
7. Later `--from-dir` hydrate runs only call `getPosts` for URIs that are not `ok`, using `public.api.bsky.app`.
8. Saves are a header and no rows. Unfollows and deletions are not generated.
9. A live `--limit 3 --hydrate none` run writes under `experiments/data_request_2026_08_14/data/`.

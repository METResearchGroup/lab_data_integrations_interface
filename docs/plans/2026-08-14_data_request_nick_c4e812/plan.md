# Deliver Nick's 12-month Bluesky extract for the greedy-10 cohort

## Remember
- Exact file paths always
- Exact commands with expected output
- DRY, YAGNI, TDD, frequent commits
- Delegated tasks must be impossible to misread.

## Overview

Turn `experiments/data_request_2026_08_14/greedy10_dedup_members.csv` (8,431 DIDs) into a timestamped CSV bundle covering the fields in `experiments/data_request_2026_08_14/REQUEST_DETAILS.md` over a trailing 12-month window. File and column contracts live in `experiments/data_request_2026_08_14/EXPECTED_FILES.md`. Reuse the getRepo decode path in `experiments/aoc_getrepo_derived_stats_2026_08_11/`, then add AppView profile fields and post lookups so activity rows can join to a posts table.

## Happy flow

An operator runs one experiment entrypoint. The job reads the greedy-10 DID list and pulls each public repo. It looks up referenced posts into one posts table, and it writes activity and graph tables under `experiments/data_request_2026_08_14/data/<timestamp>/`. Saves are an empty schema file. Unfollows are omitted.

```mermaid
flowchart TD
  input["greedy10_dedup_members.csv"] --> profiles["AppView profiles"]
  input --> repos["getRepo per DID"]
  repos --> decode["Decode posts likes reposts follows"]
  decode --> window["Keep actor records in 12-month window"]
  window --> hydrate["AppView getPosts for referenced URIs"]
  hydrate --> posts["posts.csv"]
  window --> events["likes reposts quotes replies originals"]
  events --> posts
  profiles --> out["Timestamped folder"]
  posts --> out
  events --> out
  window --> graph["follow_edges.csv inside the cohort"]
  graph --> out
```

## Approach

Keep post text and counts in `posts.csv` once. Activity files store the actor, the event id, timestamps, and post URI join keys. Public repos are the source of what each person did. AppView is the source of handles, bios, platform follower counts, and target posts fetched by URI. Do not invent private bookmarks or deleted follows.

## Steps

### Step 1: Freeze window, cohort, and output contracts

Lock the 12-month bound, the 8,431-DID input, and the schemas in `experiments/data_request_2026_08_14/EXPECTED_FILES.md`. Add failing tests that check written CSV headers against that doc. See [steps/step1.md](steps/step1.md).

### Step 2: Profile fields for every DID

Resolve current handle, display name, bio, and follower/followee counts via public AppView profile calls. Write the profiles table. Account createdAt comes from the getRepo profile record in Step 3. See [steps/step2.md](steps/step2.md).

### Step 3: getRepo fetch and decode

Download each repo through the existing relay getRepo and decode helpers. Keep posts, likes, reposts, follows, and the profile record. Record per-DID failures without aborting the cohort. See [steps/step3.md](steps/step3.md).

### Step 4: Activity tables, posts table, and lookups

Filter actor records to the window. Write originals, likes, reposts, quotes, and replies. Put cohort-authored posts and like/repost/quote/reply targets into `posts.csv`, filling bodies and counts from AppView when present. Write an empty saves file. See [steps/step4.md](steps/step4.md).

### Step 5: Follows, write outputs, and smoke

Build current follow edges where both ends are in the cohort (`follow_edges.csv`). Write follow creates during the window that still exist. Write errors and run metadata. Smoke a small DID subset before the full 8,431. See [steps/step5.md](steps/step5.md).

## What "done" looks like

1. Per-step specs exist under `docs/plans/2026-08-14_data_request_nick_c4e812/steps/`.
2. `experiments/data_request_2026_08_14/EXPECTED_FILES.md` is the schema source of truth.
3. Experiment code lives under `experiments/data_request_2026_08_14/` and imports decode helpers from `experiments/aoc_getrepo_derived_stats_2026_08_11/` and `experimentation/aoc_followers_backfill/` rather than copying decode code.
4. A timestamped run folder contains every generated file named in `EXPECTED_FILES.md`, with columns matching that doc.
5. Activity tables join to `posts.csv` on post URIs. `follow_edges.csv` is the single file for follows inside the cohort.
6. Saves are a header and no rows. Unfollows and deletions are not generated.
7. Missing target posts keep their URI in the activity table and a `posts.csv` row whose `hydration_status` is not `ok`.
8. A live subset run writes under `experiments/data_request_2026_08_14/data/`.

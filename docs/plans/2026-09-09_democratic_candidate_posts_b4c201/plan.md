# Pull Iceberg posts that name five Democratic candidates

## Remember

- Exact file paths always
- Exact commands with expected output
- DRY, YAGNI, TDD, frequent commits
- Delegated tasks must be impossible to misread.

## Overview

[Issue 201](https://github.com/METResearchGroup/lab_data_integrations_interface/issues/201) is a request for Bluesky posts about Abdul El-Sayed, James Talarico, Xavier Becerra, Roy Cooper, and Jon Ossoff. Daniel asked Billy for common criticisms from the center and from the left, from each candidate's 2026 primary onward, so a conjoint can use realistic language. The method Mark wrote on the issue is substring search on names against the posts the lab already holds, then one compiled Parquet file.

The public query UI cannot run a name substring search. The UI filters Iceberg tables by date only, returns at most 1000 rows, and writes CSV. The implementer will add a one-run experiment that exports matching posts through Athena and writes Parquet files to S3.

Detailed steps live in [`steps/`](steps/).

## Happy flow

An operator with AWS credentials for `us-east-2` runs one experiment command from the repo root. For each candidate, Athena exports Iceberg posts whose text contains an approved name string and whose creation time falls in the candidate query window. Athena writes Parquet parts under the experiment S3 prefix. The script merges those parts into one Parquet file per candidate, uploads that file to S3, and prints a progress table with one row per finished query. After all candidates finish, the script writes a combined Parquet file and a metadata file to the same S3 prefix.

```mermaid
flowchart TD
  start[Run experiment entrypoint] --> perCandidate[For each candidate]
  perCandidate --> sql[Build name-match query for that person and date window]
  sql --> athena[Athena writes Parquet parts to S3]
  athena --> merge[Merge parts and upload one Parquet per person]
  merge --> table[Print progress table with person, query, row count, S3 path]
  table --> perCandidate
  table --> compile[Upload combined Parquet and metadata to S3]
  compile --> done[Operator uses the S3 files]
```

## Approach

The implementer puts the work in a one-run experiment under [`experiments/client_request_2026_09_09/`](../../../experiments/client_request_2026_09_09/), and copies the Athena UNLOAD plus Parquet merge sequence from [`experiments/perspective_api_labeling_2026_08_11/download_posts_by_day.py`](../../../experiments/perspective_api_labeling_2026_08_11/download_posts_by_day.py). The Perspective labeling script already exports Iceberg posts to Parquet through Athena, so the new experiment can reuse that sequence. Queries run through the shared Athena helper in [`lib/aws/athena.py`](../../../lib/aws/athena.py) so the experiment uses the same client as the query UI. Durable files stay in S3. The query UI does not gain a text filter. Posts are not classified as criticisms or as coming from the center or the left. Metadata records that the file is a name match, not a criticism sample.

Jetstream coverage of `bluesky_raw.posts` starts on 2026-08-01, the coverage start date in [`bluesky_ingestion_jetstream/constants.py`](../../../bluesky_ingestion_jetstream/constants.py). The Talarico, Cooper, Ossoff, and Becerra primaries happened before 2026-08-01, so their query windows start on 2026-08-01 rather than on the primary. El-Sayed's Michigan primary is 2026-08-04, so his window can start on the primary. Historical backfill data is out of scope, because it is not in the Iceberg posts table the query path uses.

### Confirmed decisions

1. **Source table.** Query `bluesky_raw.posts` only. Likes, reposts, and follows are out of scope.
2. **Match rule.** Case-insensitive substring match on post text. No language filter. No reply filter. No toxicity or stance model.
3. **Query start.** For each candidate, the later of that candidate's primary date and 2026-08-01. Query end is the UTC date of the run, inclusive.
4. **Primary dates to confirm in code:**
   - James Talarico, Texas Senate Democratic primary, 2026-03-03
   - Roy Cooper, North Carolina Senate Democratic primary, 2026-03-03
   - Jon Ossoff, Georgia Senate Democratic primary, 2026-05-19
   - Xavier Becerra, California gubernatorial top-two primary, 2026-06-02
   - Abdul El-Sayed, Michigan Senate Democratic primary, 2026-08-04
   If a date is wrong, change only the constants and the tests that pin them.
5. **Name strings.** Distinctive surnames may match alone (El-Sayed with hyphen and spacing variants, Talarico, Ossoff). Cooper and Becerra require the given name plus the surname, because Cooper and Becerra are common surnames. Include the issue's misspelling "Beccera" as an extra Becerra string.
6. **Export shape.** One Athena export per candidate, then a compile. A post that names two candidates appears twice, once per candidate.
7. **Row cap.** The full run has no row limit. A smoke flag caps each export at 100 rows so an operator can prove AWS wiring without scanning every day.
8. **Product code.** Do not change `backend/`, `bluesky_ingestion_jetstream/`, `data_platform/`, or `ui/`.
9. **Reuse.** Import Athena from `lib/aws/athena.py`. Keep S3 helpers inside the experiment package, matching `download_posts_by_day.py`, rather than adding download methods to [`lib/aws/s3.py`](../../../lib/aws/s3.py).
10. **Code home.** All experiment code lives under [`experiments/client_request_2026_09_09/`](../../../experiments/client_request_2026_09_09/). Tests live under [`tests/experiments/client_request_2026_09_09/`](../../../tests/experiments/client_request_2026_09_09/).
11. **S3 layout.** Bucket is `lab-data-integrations-interface`. Prefix is `experiments/client_request_2026_09_09`. A run writes under `s3://lab-data-integrations-interface/experiments/client_request_2026_09_09/<run_timestamp>/`. Athena UNLOAD parts stay at `unload/<candidate_id>/`. The merged per-person Parquet is `<candidate_id>.parquet`. Combined outputs are `posts.parquet` and `metadata.json`. Do not delete S3 objects after a successful export.
12. **Progress table.** After each candidate query finishes, print a markdown table to stdout with columns Person, Query, Total results, S3 path. Person is the display name. Query is the UNLOAD SQL that ran. Total results is the merged row count. S3 path is the merged per-person Parquet URI. Reprint the full table of finished candidates each time, so the operator sees progress as each query completes.

## Steps

### Step 1: Confirm candidates, name strings, dates, and output layout

Confirm the five people, the name strings, the query windows, the S3 prefix, and the Parquet and metadata columns. Scaffold the experiment package with stub signatures and failing contract tests. See [`steps/step1.md`](steps/step1.md).

### Step 2: Build the per-candidate Athena export SQL

Write a pure SQL builder that substring-matches the approved name strings, limits the scan to the candidate's date window, casts timestamps for Parquet export, and optionally applies the smoke row cap. No AWS calls. See [`steps/step2.md`](steps/step2.md).

### Step 3: Export, merge, and upload one Parquet file per candidate

Run each candidate's SQL through Athena, keep the UNLOAD parts in S3, merge them into one Parquet file, upload that file to S3, and record the SQL, row count, and S3 path for the progress table. See [`steps/step3.md`](steps/step3.md).

### Step 4: Compile the combined Parquet file and metadata

Concatenate the per-candidate files, write the combined Parquet file and metadata locally, then upload both to the run prefix in S3. See [`steps/step4.md`](steps/step4.md).

### Step 5: Wire the entrypoint, progress table, README, and live smoke checklist

Connect confirmation, SQL, export, compile, and the progress table in `main.py`. Ignore generated local data in git. Add mocked end-to-end tests and a live smoke command. See [`steps/step5.md`](steps/step5.md).

## What "done" looks like

1. [`experiments/client_request_2026_09_09/`](../../../experiments/client_request_2026_09_09/) exists with constants, a SQL builder, export helpers, a compile step, a progress table helper, `main.py`, and a README.
2. Unit tests under [`tests/experiments/client_request_2026_09_09/`](../../../tests/experiments/client_request_2026_09_09/) cover name strings, date windows, SQL shape, export, compile, the progress table, and a fully mocked run. The tests pass without AWS.
3. A full run with AWS credentials exports matching posts from `bluesky_raw.posts` for all five candidates and writes UNLOAD parts, per-person Parquet files, `posts.parquet`, and `metadata.json` under `s3://lab-data-integrations-interface/experiments/client_request_2026_09_09/<run_timestamp>/`.
4. After each candidate query, stdout reprints a markdown table with Person, Query, Total results, and S3 path for every finished candidate.
5. Metadata states that the file is a name match, records each primary date, and records that four windows start on 2026-08-01 rather than on the primary.
6. `backend/`, `bluesky_ingestion_jetstream/`, `data_platform/`, and `ui/` are unchanged.
7. Generated local Parquet files are gitignored. The query UI still has no text filter.

# Democratic candidate Iceberg post export

The experiment exports Bluesky posts whose text contains an approved name string for Abdul El-Sayed, James Talarico, Xavier Becerra, Roy Cooper, and Jon Ossoff. The rows are name matches on post text. They are not posts labeled as criticisms, and they are not sorted into center or left language.

## Coverage dates

Jetstream Iceberg coverage of `bluesky_raw.posts` begins on 2026-08-01. Query windows start on the later of the candidate's primary date and 2026-08-01. Four primaries (Talarico, Cooper, Ossoff, and Becerra) are earlier than 2026-08-01, so those windows start on 2026-08-01. El-Sayed's Michigan primary is 2026-08-04, so that window starts on 2026-08-04.

## AWS

Use AWS credentials for `us-east-2`. Athena queries Glue database `bluesky_raw` in workgroup `bluesky_raw_maintenance`. The S3 bucket is `lab-data-integrations-interface`. The prefix is `experiments/client_request_2026_09_09`.

## Commands

From the repo root:

```bash
PYTHONPATH=. uv run python experiments/client_request_2026_09_09/main.py
PYTHONPATH=. uv run python experiments/client_request_2026_09_09/main.py --smoke
PYTHONPATH=. uv run python experiments/client_request_2026_09_09/main.py --candidate cooper
PYTHONPATH=. uv run python experiments/client_request_2026_09_09/main.py --smoke --candidate el_sayed
```

`--smoke` caps each candidate export at 100 rows. `--candidate` exports one `candidate_id` and compiles a combined file that contains only that candidate's rows.

## Outputs

A run writes these objects under the timestamped prefix:

- `s3://lab-data-integrations-interface/experiments/client_request_2026_09_09/<run_timestamp>/posts.parquet`
- `s3://lab-data-integrations-interface/experiments/client_request_2026_09_09/<run_timestamp>/metadata.json`

Per-candidate merged files are `<candidate_id>.parquet` under the same prefix. Athena UNLOAD parts stay under `unload/<candidate_id>/` and are not deleted after a successful export. Local copies land in `experiments/client_request_2026_09_09/data/<run_timestamp>/`.

The full compiled file from the 2026-09-10 run is also in git:

- `experiments/client_request_2026_09_09/outputs/2026_09_10-02:22:55/posts.parquet`

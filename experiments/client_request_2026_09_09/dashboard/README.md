# Candidate post explorer

A small HTML page for scrolling Iceberg posts that name Abdul El-Sayed, James Talarico, Xavier Becerra, Roy Cooper, and Jon Ossoff. Filter by person. Search post text. Each row shows `created_at`, the matched name string, the post text, the AT-URI (linked on bsky.app when possible), the author DID, and `matched_candidate`.

The file is a name match, not a criticism-coded sample.

## Data

The explorer reads gzipped JSON uploaded next to the experiment Parquet files:

`s3://lab-data-integrations-interface/experiments/client_request_2026_09_09/<run_timestamp>/dashboard/<candidate_id>.json.gz`

`config.js` holds seven-day presigned GET URLs for those objects. It is generated and gitignored. Copy `config.example.js` to `config.js` only for layout work; a live session needs `prepare_data.py`. Rebuild it before a review session if the URLs have expired.

## Prepare

From the repo root, after a full export has written local Parquet files:

```bash
PYTHONPATH=. uv run python experiments/client_request_2026_09_09/dashboard/prepare_data.py
```

## Local

```bash
python -m http.server 4173 --directory experiments/client_request_2026_09_09/dashboard
```

Then open `http://127.0.0.1:4173`.

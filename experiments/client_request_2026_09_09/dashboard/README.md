# Candidate post explorer

A small HTML page for scrolling Iceberg posts that name Abdul El-Sayed, James Talarico, Xavier Becerra, Roy Cooper, and Jon Ossoff. Filter by person. Search post text. Each row shows `created_at`, the matched name string, the post text, the AT-URI (linked on bsky.app when possible), the author DID, and `matched_candidate`.

The file is a name match, not a criticism-coded sample.

## Data

`config.js` points at gzipped JSON under `data/<candidate_id>.json.gz`. Those files are committed so a static local server can load them. `prepare_data.py` rebuilds them from the local Parquet export and uploads a copy to S3.

The Vercel host does not ship the gzip files. It loads them through `/api/posts?candidate=<id>`, which signs a GET of the matching S3 object.

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

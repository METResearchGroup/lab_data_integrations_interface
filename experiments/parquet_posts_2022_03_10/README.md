# Iceberg posts parquet → CSV → Bluesky links (2022-03-10)

Take one `bluesky_raw.posts` Iceberg data file from S3, convert it to CSV,
list the post AT-URIs, hydrate each unique URI with public AppView
`app.bsky.feed.getPosts`, and write web links plus records as JSONL.

## Source

`s3://lab-data-integrations-interface/bluesky/raw/posts/data/created_at_day=2022-03-10/00000-38-5a249a3c-fde3-4340-adbd-3a235f0fa83b.parquet`

The file has 20 rows and 10 unique post URIs (each URI appears twice, matching
Jetstream at-least-once delivery before weekly Iceberg dedup).

## Run

From the repo root:

```bash
PYTHONPATH=. uv run python -m experiments.parquet_posts_2022_03_10.main
```

## Outputs

- `data/posts.csv` — every row from the parquet file
- `data/post_links.jsonl` — one line per unique URI, with `url` and `record`

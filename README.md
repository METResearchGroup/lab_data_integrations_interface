# Lab Data Integrations Interface

## Summary

A social data platform for academic researchers. It maintains a multi-TB dataset of Bluesky data and puts it behind a natural-language query interface, so getting a dataset for a paper takes minutes rather than the weeks that collecting it yourself would.

Our project is split into 3 major components:

1. **Bluesky ingestion jetstream** — collects live data off the Bluesky firehose into Iceberg tables, plus the scheduled job that keeps those tables healthy.
2. **Bluesky backfill app** — historical backfills of Bluesky users.
3. **Agentic Querying engine** - an agentic query engine that turns a researcher's question into a dataset they can download.

## bluesky_ingestion_jetstream

### Ingestion

![Bluesky ingestion architecture](docs/images/bluesky_ingestion_jetstream.png)

**Flushing:** buffers are flushed together to Iceberg on S3 once the set hits 2GB or 30 minutes, whichever comes first. Each record type commits separately, and a batch that fails its retries is dead-lettered to S3.

**Cursor checkpointing:** the cursor is written to DynamoDB after every flush, so it never gets ahead of a row that is not yet durable.

### Table maintenance

![Bluesky table maintenance architecture](docs/images/bluesky_table_maintenance.png)

One state machine, one job per schedule. `OPTIMIZE` runs daily over the last few days (and unbounded weekly) to bin-pack small files, `dedup` weekly to delete duplicate rows the stream produced, and `VACUUM` weekly to expire snapshots and sweep what they orphan. Step Functions failures raise a CloudWatch alarm that emails through SNS.

## backend/agentic_search

```mermaid
flowchart LR
  Q[Natural-language query] --> V[validate]
  V -- valid --> G[generate SQL] --> E[execute on Athena] --> M[Email results]
  V -. invalid .-> M
```

**Validation before SQL:** one LLM call turns the question into a `QueryIntent` (record type, columns, date range, and any post-text keywords). That intent is then checked in plain code — nonsense input, columns the table does not have, dates outside coverage, a keyword filter on anything but posts, a keyword filter with either date open, a blank term, or a term list past the cap (8 terms, 80 characters each). An invalid query stops there and never reaches Athena.

**Keyword filters:** `keywords` empty means no text filter. Otherwise `generate_sql` matches `text` with a case-insensitive `regexp_like`. The model still supplies only the intent; the predicate is built in code. `any` is one alternation. `all` is a separate predicate per term, AND-ed. `whole_word` wraps each term in an ASCII `\b` boundary. A `matched_keywords` column records the first term that hit. The scan estimate includes `text` for these queries, including when the question did not select that column.

Limits of that filter:

- Matching is literal. There is no stemming and no ranking. Rows come back in `created_at` order.
- Cost scales with the days scanned. The filter reads `text` for every day in the range, which is what the 10 GB cap is counting.
- Word boundaries are ASCII. They do not fall between characters in Chinese, Japanese, or Korean text, so those terms are extracted with `whole_word` off and match as substrings.
- A mention matches the handle as it is written in the post text, such as `@name.bsky.social`. It matches that character sequence, not the author's DID and not a handle stored outside the post.
- `#` and `@` are not word characters, and Athena's regex engine has no lookbehind, so a `\b` in front of them does not match. Hashtags and mentions are substring matches. `#climate` also matches `#climatechange`.

**Async by design:** the endpoint acknowledges with `202` and hands the work to a background task, so a long Athena scan never blocks the request. Every outcome — results, validation issues, or an error — is mailed.

## Repository map

| Directory | Role |
|-----------|------|
| `bluesky_ingestion_jetstream` | The ingestion process: Jetstream WebSocket, commit parsing, in-memory buffers, Iceberg sink, cursor tracking, telemetry |
| `backend/agentic_search` | The query engine: LangGraph app, intent extraction and validation, SQL generation, Athena execution, result mail |
| `backend/routes` | FastAPI endpoints the UI calls |
| `ui` | Next.js query console |
| `terraform` | Infrastructure for both: S3 bucket, Glue database, cursor table, and the Athena/Step Functions maintenance job with its alarm |

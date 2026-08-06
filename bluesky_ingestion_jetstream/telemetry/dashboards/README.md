# Jetstream ingestion dashboard

`jetstream_ingestion.json` — live at
[/d/bluesky-jetstream-ingestion](https://jumbolaurel1950.grafana.net/d/bluesky-jetstream-ingestion).

Datasource uids are hardcoded to this stack (`grafanacloud-prom`,
`grafanacloud-logs`), so the file posts straight to the API. Editing it in the
UI and pasting the result into the v2-schema JSON editor will not work — this is
schema v1. Edit the file, then push:

```bash
TOKEN='glsa_…'   # service account token, dashboards:write
curl -sS -X POST https://jumbolaurel1950.grafana.net/api/dashboards/db \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"dashboard\": $(cat bluesky_ingestion_jetstream/telemetry/dashboards/jetstream_ingestion.json), \"overwrite\": true}"
```

`overwrite` keys off the `bluesky-jetstream-ingestion` uid, so this updates in
place rather than making a copy.

## Panels

| Panel | Source |
|---|---|
| Socket, cursor value, socket disconnects, dead letters, dropped rows | Mimir |
| Rows / data ingested by record type | Mimir |
| Per-flush detail | Loki, `event="flush"` JSON line |
| Socket disconnects by reason | Mimir |
| Disconnects, dead letter writes | Loki |

The last three sit in a collapsed **Diagnostics** row at the bottom — drill-down
for when a top tile goes red, not everyday reading.

The Mimir panels use `$__range`, so they follow the time picker rather than a
fixed 24h window. Dashboard default is `now-24h`.

Volume is in **GB** on the range total and **MB** in the per-flush table. The
counter is bytes either way; the divisor lives in the query (`/ 1e9`), and the
table's MB come straight from `get_flush_payload`.

The range total's unit is `suffix:GB`, not Grafana's `decgbytes`: the built-in
byte units rescale to whatever fits, so a 44 MB day renders as "44.08 MB" under
`decgbytes`. A plain suffix pins it to GB, at the cost of reading "0.04 GB" on
light days.

Both bar gauges run one query per record type — likes, posts, reposts, follows
— so the bars hold that order instead of sorting by value. Adding a record type
means adding a fifth query to each.

## Metric names

Mimir rewrites OTLP names on ingest. Confirmed against the stack:

| Emitted | In Mimir |
|---|---|
| `bluesky_jetstream.rows.written` | `bluesky_jetstream_rows_written_total` |
| `bluesky_jetstream.bytes.written` | `bluesky_jetstream_bytes_written_total` |
| `bluesky_jetstream.connection_failures` | `bluesky_jetstream_connection_failures_total` |
| `bluesky_jetstream.dead_letters` | `bluesky_jetstream_dead_letters_total` |
| `bluesky_jetstream.dropped` | `bluesky_jetstream_dropped_total` |
| `bluesky_jetstream.cursor.timestamp` | `bluesky_jetstream_cursor_timestamp_seconds` |
| `bluesky_jetstream.connected` | `bluesky_jetstream_connected_ratio` |

The `By` unit adds no suffix, but `s` and `1` do — `connected` becomes
`connected_ratio`, which is the one name nothing would have guessed. Re-check
after any instrument change:

```promql
group by (__name__) ({__name__=~"bluesky.*"})
```

`bluesky_jetstream_reconnects_total` also lingers in the stack from an earlier
version of the instruments; nothing emits it now and no panel reads it.

## Alert

`dropped > 0` is the one condition worth alerting on: rows nothing durable
accepted. From the **Dropped rows** panel → **More → New alert rule**, with

```promql
sum(increase(bluesky_jetstream_dropped_total[10m])) > 0
```

Set **No data** to OK — the counter has no series until it first fires.

## Empty panels

`dead_letters` and `dropped` have no series yet — nothing has gone wrong, so
those stats read `0` from `noValue`. Gauges report every export. Metrics land
every 60s, logs every ~5s, which is why the disconnects-by-reason panel uses
`$__rate_interval`: `$__interval` can fall below the 60s export interval on a
short range and return nothing.

The per-flush table runs four transforms in order: `extractFields` expands
Loki's `labels` map into columns (without it the panel shows a Time column and
nothing else), `convertFieldType` makes the 10 numeric fields sort numerically,
`filterFieldsByName` whitelists `Time`, `reason` and the `_rows`/`_mb` fields,
and `organize` fixes column order. The whitelist beats hiding fields one by one:
`| json` also surfaces a dozen OTel resource attributes (`code_file_path`,
`telemetry_sdk_version`, trace ids …).

The Socket tile has three states, not two: `1` → Alive (green), `0` → Dead
(red), and no series at all → "Not reporting", which means the process stopped
exporting rather than the socket dropping.

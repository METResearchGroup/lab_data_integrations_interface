# How to Set Up the Grafana Dashboard

## Overview

`bluesky_ingestion_jetstream/telemetry/dashboards/jetstream_ingestion.json` is
the Jetstream ingester's dashboard, checked into the repo. This runbook covers
importing it into a Grafana Cloud stack.

The dashboard reads from two datasources: the stack's hosted Mimir (metrics) and
Loki (logs). Both are provisioned automatically with every Grafana Cloud stack —
there is no datasource to create.

## Prerequisites

- A Grafana Cloud account with a stack provisioned.
- The ingester exporting to that stack. See
  [HOW_TO_ADD_OBSERVABILITY_GRAFANA.md](HOW_TO_ADD_OBSERVABILITY_GRAFANA.md) for
  the OTLP wiring; the dashboard is a view over that data and shows nothing
  without it.

Metrics export every 60s and logs every ~5s, so allow a minute after the first
run before the panels fill in.

## Import

1. In your stack, go to **Dashboards → New → Import**.
2. **Upload dashboard JSON file**, and pick
   `bluesky_ingestion_jetstream/telemetry/dashboards/jetstream_ingestion.json`.
3. **Import**.

That lands you on the dashboard, at `/d/bluesky-jetstream-ingestion`.

Import is idempotent: the JSON carries the uid `bluesky-jetstream-ingestion`, so
re-importing after pulling a newer version of the file updates the existing
dashboard rather than making a second copy.

## Verifying

Set the time picker to **Last 24 hours**. Expect:

- **Socket** — `Alive`. `Dead` means the websocket dropped; "Not reporting"
  means the process stopped exporting entirely.
- **Cursor value** — a timestamp within one flush interval of now.
- **Data Ingested** and **Total ingested** — non-zero once a flush has landed.
- **Per-flush detail** — one row per flush, newest first.
- **Dead letters** and **Dropped rows** — green zeros. These counters have no
  series until something goes wrong, which is not a broken panel.

For panel-by-panel notes — metric names, units, and the transforms behind the
per-flush table — see the
[dashboard README](../../bluesky_ingestion_jetstream/telemetry/dashboards/README.md).

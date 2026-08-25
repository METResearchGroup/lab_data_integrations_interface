<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [Combining backfill and Jetstream](#combining-backfill-and-jetstream)
  - [Cutoff](#cutoff)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# Combining backfill and Jetstream

(Notes on how to combine these two pipelines)

## Cutoff

We'll set a cutoff of August 1st, 2026. Records are routed by event timestamp:

- **Before 2026-08-01** — owned by the backfill app (`getRepo`-based historical ingestion).
- **On or after 2026-08-01** — owned by the Jetstream ingestion (live firehose).

Anything at or after the cutoff must not be written by backfill, and anything before it must
not be written by Jetstream, so the two pipelines never contend for the same records.

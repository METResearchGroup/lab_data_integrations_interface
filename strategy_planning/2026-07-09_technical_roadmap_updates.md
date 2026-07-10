# Status update on the technical roadmap

## What's been built

Right now, we have a full V1 of the app. We've been able to implement a first pass of [the proposed system design](https://www.tldraw.com/f/SJAVL-hci-rKA7cw-CRHT).

Some notable recent PRs include:

### Data pipeline

- [Improve pipeline idempotency by implementing stage-specific deduplication](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/97)
- [Sync all records, per stage, to S3](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/93)
- [Set up Glue tables to query S3 records](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/94)
- [Adding disk cleanup to remove stale old files from past runs](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/108)

Then once those were done:

- [Create the orchestration DAG that runs the entire data pipeline](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/99)

### Frontend/backend

- [Add backend query support, connecting backend to Athena to make queries runnable on real data](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/95)
- [Wire example queries, introduced in the backend, to the frontend](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/96)
- [Deploy backend to Railway](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/101) and [frontend to Vercel](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/100).

### Observability

- [Adding backend + data pipeline telemetry](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/110), visible via a Grafana UI.

### Review of current status

We've deployed the data pipeline and set up an orchestration DAG to run the data pipeline. We also have deployed the frontend and backend. Now we have a working application with an actual live link for users to try. We have a backend that can take those queries and actually call Athena to fetch the data from S3. We also have a data pipeline that can continuously get new data. We've also wired observability into the apps.

## What's next

We're now interested in seeing the direction to take the app. We've been able to establish interest from users on being able to use the app. We found that there were two requests that users had to make the app more helpful for their everyday usage:

1. Access to more data
2. Natural language search

Therefore, the next versions of the app should revolve around achieving both of these goals.

Currently, we're looking at the following as the next units of work:

- [Adding support for Jetstream backfills + more data types](https://github.com/METResearchGroup/lab_data_integrations_interface/issues/111)
- [Introducing agentic search](https://github.com/METResearchGroup/lab_data_integrations_interface/issues/116)
- Add cron jobs on common query requests, to continuously collect that data.
  - We can do this temporarily via the API for now, though to really get a lot of data we'll have to use the Bluesky firehose. If we want to collect tens of thousands of records daily, this is infeasible via API (we'll hit rate limits), and ideally we could scale this up to hundreds of thousands or even millions of daily records.

Once these are done, some things that we'll want to work on next include:

- Once we do [the Jetstream backfill support PR](https://github.com/METResearchGroup/lab_data_integrations_interface/issues/111) we should give thought to (1) supporting the firehose and (2) having the firehose running for a while. We'll want to progressively backfill all data from Bluesky using the backfill data.
- We'll want to also add support for Reddit next, as it's hard to get good data for it. We can build a search interface on top of the Reddit PushShift dataset (which is pretty ambitious! Multiple TBs of data!).
- We'll also want to improve agentic search and consider things like caching, indexing, semantic search vs. BM25, and how to evaluate the performance of the agentic search layer (e.g., retrieval relevance, query correctness, etc).

# Status update on the technical roadmap

Right now, we have ...

....
....

We've been able to establish interest from users on being able to use the app. We found that there were two requests that users had to make the app more helpful for their everyday usage:

1. Access to more data
2. Natural language search

Therefore, the next versions of the app should revolve around achieving both of these goals.

Currently, we're looking at the following as the next units of work:

- [Adding support for Jetstream backfills + more data types](https://github.com/METResearchGroup/lab_data_integrations_interface/issues/111)
- [Introducing agentic search](...)

Once these are done, some things that we'll want to work on next include:

- Once we do [the Jetstream backfill support PR](https://github.com/METResearchGroup/lab_data_integrations_interface/issues/111) we should give thought to (1) supporting the firehose and (2) having the firehose running for a while. We'll want to progressively backfill all data from Bluesky using the backfill data.
- We'll want to also add support for Reddit next, as it's hard to get good data for it. We can build a search interface on top of the Reddit PushShift dataset (which is pretty ambitious! Multiple TBs of data!).
- We'll also want to improve agentic search and consider things like caching, indexing, semantic search vs. BM25, and how to evaluate the performance of the agentic search layer (e.g., retrieval relevance, query correctness, etc).

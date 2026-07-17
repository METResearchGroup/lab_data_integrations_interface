<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents** 

- [Design Doc: Natural language search](#design-doc-natural-language-search)
  - [Purpose](#purpose)
  - [Background](#background)
  - [Proposal](#proposal)
    - [High-level architecture](#high-level-architecture)
    - [User-facing behavior](#user-facing-behavior)
    - [Goals/non-goals](#goalsnon-goals)
      - [What is in-scope](#what-is-in-scope)
      - [What is out-of-scope](#what-is-out-of-scope)
    - [Estimated scale](#estimated-scale)
    - [Scope of changes](#scope-of-changes)
  - [Implementation details](#implementation-details)
    - [Per-service/component changes](#per-servicecomponent-changes)
      - [Frontend](#frontend)
      - [Backend](#backend)
      - [Athena client](#athena-client)
      - [New service layers](#new-service-layers)
        - [LLM orchestration layer](#llm-orchestration-layer)
        - [Validation layer](#validation-layer)
        - [Query policy layer](#query-policy-layer)
        - [Job-state layer](#job-state-layer)
        - [Result artifact layer](#result-artifact-layer)
        - [Retrieval/cache layer](#retrievalcache-layer)
        - [API Gateway](#api-gateway)
    - [Schemas/APIs](#schemasapis)
      - [Creating a search job](#creating-a-search-job)
      - [Get job status](#get-job-status)
      - [Job states](#job-states)
      - [Error shape](#error-shape)
    - [Prompting](#prompting)
      - [Draft query generation prompt](#draft-query-generation-prompt)
      - [Draft router prompt](#draft-router-prompt)
      - [Testing + Experimentation](#testing--experimentation)
    - [Adding limits by default](#adding-limits-by-default)
    - [Gating on the `EXPLAIN ANALYZE` query](#gating-on-the-explain-analyze-query)
    - [Validation rules](#validation-rules)
      - [Router layer validation](#router-layer-validation)
      - [Validating generated SQL queries](#validating-generated-sql-queries)
      - [Post-Athena validation/postprocesisng](#post-athena-validationpostprocesisng)
    - [Caching design](#caching-design)
      - [Option 1: Matching on other entities or values](#option-1-matching-on-other-entities-or-values)
      - [Option 2: Fuzzy matching](#option-2-fuzzy-matching)
      - [Option 3: Hybrid RAG (semantic search + BM25)](#option-3-hybrid-rag-semantic-search--bm25)
      - [Erring towards RAG rather than Redis](#erring-towards-rag-rather-than-redis)
    - [LLM application deployment to production](#llm-application-deployment-to-production)
      - [Deploying LLM pipeline changes to production](#deploying-llm-pipeline-changes-to-production)
        - [1. Define the proposed change and hypothesis](#1-define-the-proposed-change-and-hypothesis)
        - [2. Create an isolated candidate configuration](#2-create-an-isolated-candidate-configuration)
        - [3. Run deterministic tests](#3-run-deterministic-tests)
        - [3. Run offline evals](#3-run-offline-evals)
        - [4. Test in a dev environment](#4-test-in-a-dev-environment)
        - [5. Shadow mode](#5-shadow-mode)
        - [6. Canary](#6-canary)
        - [7. Release to production](#7-release-to-production)
      - [Offline evals strategy](#offline-evals-strategy)
    - [Observability/Telemetry](#observabilitytelemetry)
      - [System Ops](#system-ops)
        - [General System Ops considerations](#general-system-ops-considerations)
        - [Service-level indicators and objectives](#service-level-indicators-and-objectives)
        - [Latency/performance metrics](#latencyperformance-metrics)
        - [Reliability](#reliability)
        - [Logging](#logging)
        - [Deployment and change management](#deployment-and-change-management)
        - [Incident response and runbooks](#incident-response-and-runbooks)
        - [Data retention and privacy](#data-retention-and-privacy)
      - [LLMOps](#llmops)
        - [General LLMOps considerations](#general-llmops-considerations)
        - [1. Was the LLM result correct?](#1-was-the-llm-result-correct)
        - [2. Was the LLM behavior reliable, observable, and cost-efficient?](#2-was-the-llm-behavior-reliable-observable-and-cost-efficient)
        - [3. Can we audit and reconstruct how the result was produced?](#3-can-we-audit-and-reconstruct-how-the-result-was-produced)
        - [Tracking LLMOps in a dashboard](#tracking-llmops-in-a-dashboard)
      - [FinOps](#finops)
        - [FinOps principles](#finops-principles)
        - [Cost model](#cost-model)
        - [Controlling Athena costs](#controlling-athena-costs)
        - [Controlling LLM costs](#controlling-llm-costs)
        - [Controlling cache costs](#controlling-cache-costs)
        - [Controlling storage and result-retention costs](#controlling-storage-and-result-retention-costs)
    - [Scaling how we manage query results](#scaling-how-we-manage-query-results)
      - [Guiding principles to consider](#guiding-principles-to-consider)
      - [A tiered management policy](#a-tiered-management-policy)
        - [Small results](#small-results)
        - [Medium results](#medium-results)
        - [Large results](#large-results)
      - [Proposed V1](#proposed-v1)
      - [Async job model](#async-job-model)
      - [Materialized-result design](#materialized-result-design)
  - [Cross-cutting concerns](#cross-cutting-concerns)
    - [Security and authorization](#security-and-authorization)
    - [Idempoptency and duplicate requests](#idempoptency-and-duplicate-requests)
    - [Configuration and environment management](#configuration-and-environment-management)
    - [Failure isolation and degraded behavior](#failure-isolation-and-degraded-behavior)
    - [Consistency and state transitions](#consistency-and-state-transitions)
    - [User experience and explainability](#user-experience-and-explainability)
    - [Maintainability and ownership](#maintainability-and-ownership)
  - [Errata](#errata)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# Design Doc: Natural language search

This is a design doc for the natural language search component.

## Purpose

This document proposes a natural-language search interface for the existing research data platform.

The system will allow users to describe the data they need in plain language, translate that request into a validated Athena SQL query, execute the query, and return the resulting dataset through a downloadable artifact.

The design covers the end-to-end request lifecycle, including:

- Natural-language request intake.
- Request routing and validation.
- SQL generation and deterministic safeguards.
- Query-cost controls.
- Athena execution.
- Result materialization and delivery.
- Caching and reuse of prior results.
- LLMOps, System Ops, and FinOps considerations.

The primary goal is to make the platform accessible to researchers who understand the data they need but may not know the underlying schemas or be comfortable writing SQL.

This document also defines the operational boundaries for a V1 implementation. In particular, the system should prioritize correctness, bounded cost, and safe failure behavior over supporting every possible query or large-scale export.

## Background

The existing interface exposes a relatively direct path from the FastAPI application to Athena. This works for users who already understand the available tables, columns, joins, and SQL dialect, but it places a significant burden on less technical researchers.

To retrieve data successfully, a user currently needs to know:

- Which datasets contain the relevant information.
- The names and meanings of tables and columns.
- How datasets relate to one another.
- How to express the request as valid Athena SQL.
- How to constrain the query so that it does not scan or return an unreasonable amount of data.

This creates several problems.

- First, it limits access to users with sufficient SQL and data-platform knowledge. Researchers may understand their substantive research question while still needing engineering support to translate it into a query.
- Second, direct user-generated SQL creates operational and financial risk. A syntactically valid query may still reference the wrong data, scan an excessive number of records, return an unusably large result, or fail because of incorrect assumptions about the schema.
- Third, the current interaction model does not provide a structured place for request validation, cost estimation, query reuse, asynchronous execution, or result lifecycle management.

Recent improvements to LLMs make natural-language-to-SQL a feasible interface for this use case, particularly because the application is constrained to a known set of datasets and relatively narrow request types. However, an LLM-generated query should not be executed directly. The model should be treated as one component in a broader system containing deterministic validation, cost controls, observability, and explicit failure handling.

The proposed design therefore introduces a guarded natural-language query pipeline on top of the existing data platform. The system will use LLMs to interpret requests and generate candidate SQL, while retaining deterministic application controls over what may be executed and returned.

## Proposal

Our proposal is a natural-language (NL) to SQL search interface. We propose a natural language query interface, where we take user queries, convert to SQL, execute the queries, and return results to users. Along the way, we include layers of caching and validation.

### High-level architecture

```mermaid
flowchart LR
    U["User query:<br/>'I want all posts liked by Stanley<br/>in the past 2 weeks'"]
    FE["Frontend checks,<br/>e.g., rate limits"]
    GW["API Gateway<br/>(auth, rate limits,<br/>middleware, etc)"]
    BE["Backend: Clean up user request /<br/>prevent prompt injection / jailbreak"]
    CACHE["Caching layer"]
    ROUTER{"Is this a user request<br/>that is valid? router"}

    INV["Invalid"]
    INV1["Invalid because we don't<br/>have that metadata/user"]
    INV2["Invalid because we<br/>lack the kind of data"]
    INV3["Invalid because the<br/>user request is nonsense"]
    DEF["Default response"]

    LLM["Ask an LLM to<br/>create the SQL query"]
    VAL_SQL["Validate / post-process<br/>the SQL query"]
    EXPLAIN["Run 'EXPLAIN ANALYZE'<br/>on the query"]
    EXPENSIVE["If query is too expensive, return a<br/>default response and tell them to contact<br/>the team. Can also give feedback on how<br/>to change/constrain the prompt."]
    SQL_CACHE["Check cache for SQL queries<br/>(higher priority for large queries;<br/>for smaller queries, cost of keeping<br/>in cache may not be worth it)"]
    CACHE_HIT["Return the result directly"]
    DB["On cache miss (or skip):<br/>DB / data pool executes the query"]
    VAL_RES["Validate / post-process<br/>the results"]

    U --> FE --> GW --> BE --> CACHE
    CACHE -->|"On cache hit,<br/>return to user"| U
    CACHE --> ROUTER

    ROUTER --> INV
    INV --> INV1 & INV2 & INV3 --> DEF

    ROUTER --> LLM --> VAL_SQL
    VAL_SQL -->|"Retry X times"| LLM
    VAL_SQL --> EXPLAIN
    EXPLAIN --> EXPENSIVE
    EXPLAIN --> SQL_CACHE
    SQL_CACHE --> CACHE_HIT
    SQL_CACHE --> DB --> VAL_RES
    VAL_RES --> U
    VAL_RES --> CACHE
```

### User-facing behavior

A user enters the app and enters a natural language query as well as an email for contact (how the results are returned to the user is out-of-scope of the current plan). Upon submission, the user is informed that the request is underway. They then are given an end result, currently scoped to be a presigned URL with the resulting .csv file, if the request is valid.

### Goals/non-goals

#### What is in-scope

- NL-to-SQL end-to-end pipeline.
- Validation + preprocessing/postprocessing.
- API gateway layer (for rate limiting, authorization, etc).
- Agent plane observability: adding telemetry to the app and integrating with the existing [Grafana-based telemetry plane](https://github.com/METResearchGroup/lab_data_integrations_interface/issues/113). Some key metrics we care to track include error rate, p95/p99, cache hits/misses.
- LLMOps for the LLM components (router query, SQL generation query, and RAG steps).
- Basic FinOps: we want to track the cost of supporting our expected use case. We want to understand the cost of scaling different application components as well as provide a cost basis that we can then convert into a well-structured proposal for multi-TB project expansion.

#### What is out-of-scope

- Support for expanding data availability: this is managed in [this call for proposal](https://github.com/METResearchGroup/lab_data_integrations_interface/issues/111). The current plan builds on top of the existing database.
- Expanded app interactions beyond natural-language queries: we will keep the same endpoint that exists in FastAPI, focusing on providing a NL interface for users to request data.
- Expanding to multiple data sources and data integrations: this is managed in [this call for proposal](https://github.com/METResearchGroup/lab_data_integrations_interface/issues/111). The current plan builds on top of the existing data integrations.
- Multi-agent systems: two consecutive LLM calls are more than enough. No need for multi-agent architectures.

### Estimated scale

The initial system is intended for a relatively small group of academic researchers rather than a high-volume public search product.

For V1 planning, we can assume:

- Tens of active users rather than thousands.
- Low hundreds of requests per day at peak beta usage.
- Low concurrent usage, likely fewer than 5–10 active queries at a time.
- Most users submitting a small number of highly specific requests rather than repeatedly querying the system.
- Most accepted requests returning datasets small enough to download and analyze locally.
- A small minority of requests producing large scans or exports and requiring rejection or manual handling.

The primary scalability risk is therefore not raw request throughput. It is the long-tail cost and runtime of individual queries. A single poorly constrained query may scan far more data than hundreds of ordinary requests.

As a result, we'll want to focus capacity planning on measuring metrics such as:

- Athena bytes scanned per request
- Result size
- Query runtime
- Concurrent Athena executions
- Storage consumed by generated result artifacts

The architecture should support moderate growth without redesign, but we do not need to optimize V1 for large-scale public traffic. If usage grows substantially, likely scaling steps include:

- Moving async work into a dedicated queue and worker pool.
- Separating workloads based on size.
- Introducing stricter quotas and classes.
- Expanding precomputation and query optimization.
- Adding autoscaling for API and worker services.

### Scope of changes

Here, we introduce a new product surface. We replace the existing simple FastAPI + Athena query logic with a NL query interface.

## Implementation details

### Per-service/component changes

#### Frontend

The frontend will replace the existing SQL input with a natural-language request form.  The initial form should include:

- Natural-language query
- User email or other contact info
- A confirmation that the request may be rejected or require narrowing if it is too large.

The frontend can also do some lightweight usability validation, such as minimum query length, but these are for the UX side only (more heavyweight checks are done by the backend).

Since queries are processed async, the frontend should receive a job identifier and display the current job state. It can poll a status endpoint until the job reaches `READY`, `REJECTED`, or `FAILED`. For completed jobs, the frontend should display a short summary of the interpreted result, the total time taken, total records, and download link.

#### Backend

The backend owns orchestration of the complete workflow.

Its responsibilities, as outlined in the design flow, include:

1. Accept and validate the API request.
2. Assign a `request_id` and `job_id`.
3. Normalize the natural-language input.
4. Apply deterministic request checks.
5. Check for reusable past results where applicable.
6. Run router.
7. Generate SQL for accepted requests.
8. Parse/validate SQL.
9. Estimate query cost and enforce limits.
10. Submit the query through the Athena client.
11. Track query execution.
12. Validate/materialize the result.
13. Update job status.
14. Emit tracing, metrics, and logs.

The backend should keep the LLM callers, validators, Athena client, result management, and job-state management behind separate interfaces. This makes the individual components easier to test, replace, and evaluate.

The backend should also own retry behavior. Retries should be bounded and limited to retryable failures; deterministic rejection or validation failures should not be repeatedly retried without changing the input or correction context.

#### Athena client

The Athena client should wrap the AWS Athena APIs and expose a narrower interface tailored to this application.

Its responsibilities include:

- Submitting validated read-only queries.
- Applying the correct database, catalog, workgroup, and output location.
- Estimating or retrieving query-cost information where supported.
- Polling query status.
- Cancelling queries that exceed time or policy limits.
- Returning execution metadata.
- Retrieving or referencing the result artifact.
- Translating AWS errors into stable application error types.

The client should return metadata such as:

- Athena query execution ID.
- Query status.
- Queue and execution time.
- Bytes scanned.
- Result location.
- Failure reason.
- Whether the query was cancelled or rejected by a limit.

#### New service layers

The new workflow introduces several logical service layers. These do not necessarily need to be separate deployed services in V1; they can initially be modules inside the FastAPI application.

##### LLM orchestration layer

Owns the router, SQL generator, prompt/config loading, structured-output parsing, retries, and model metadata.

##### Validation layer

Owns deterministic request and SQL validation.

##### Query policy layer

Owns cost and usage controls, such as size limits, maximum date ranges, etc.

##### Job-state layer

Stores the current state and metadata for asynchronous requests. It should support state transitions, status lookup, retry tracking, and idempotency.

##### Result artifact layer

Owns result metadata, s3 object locations, etc.

##### Retrieval/cache layer

Stores and retrieves prior requests and SQL queries. It should verify freshness and compatibility before a past result is reused.

##### API Gateway

API Gateway will provide the public entry point to the application. API Gateway should reject clearly malformed, unauthorized, or rate-limited requests before they reach the application. Domain-specific validation, LLM routing, query policy, and cost enforcement remain backend responsibilities. For V1, we can use conservative request and rate limits and adjust them after observing beta traffic.

Its initial responsibilities should include:

- Authentication and authorization integration.
- Request-size limits.
- Per-user or per-key rate limiting.
- Basic request-schema enforcement.
- CORS configuration.
- TLS termination.
- Request correlation headers.
- Routing requests to the FastAPI backend.

### Schemas/APIs

The API should represent each request as an asynchronous search job.

#### Creating a search job

`POST /search/jobs/`

Example request:

```json
{
  "query": "I want all posts liked by Stanley in the past two weeks",
  "email": "user@example.com"
}
```

Example resopnse:

```json
{ "job_id": "job_123", "request_id": "req_123", "status": "PENDING", "created_at": "2026-07-11T15:00:00Z", "status_url": "/v1/search/jobs/job_123" }
```

The endpoint should return `202 Accepted` because the result is not expected to be available immediately.

#### Get job status

`GET /search/jobs/{job_id}`

Example in-progress response:

```json
{
  "job_id": "job_123",
  "status": "EXECUTING",
  "message": "Your query is currently running.",
  "created_at": "2026-07-11T15:00:00Z",
  "updated_at": "2026-07-11T15:00:08Z"
}
```

Example completed response:

```json
{
  "job_id": "job_123",
  "status": "READY",
  "message": "Your result is ready.",
  "result": {
    "result_id": "result_123",
    "row_count": 12500,
    "size_bytes": 4200000,
    "format": "csv",
    "download_url": "...",
    "expires_at": "2026-07-18T15:00:00Z"
  }
}
```

Example rejected response:

```json
{
  "job_id": "job_123",
  "status": "REJECTED",
  "error": {
    "code": "QUERY_TOO_EXPENSIVE",
    "message": "This request is too large for automatic execution. Try narrowing the date range or selecting fewer fields."
  }
}
```

#### Job states

The initial set of job states is:

- PENDING
- ROUTING
- GENERATING_SQL
- VALIDATING
- ESTIMATING_COST
- QUEUED
- EXECUTING
- POSTPROCESSING
- READY
- REJECTED
- FAILED
- EXPIRED

State transitions should be validated by the backend so that, for example, a failed or expired job cannot later be marked as executing.

#### Error shape

All API errors should use a consistent structure:

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "The request could not be processed.",
    "request_id": "req_123",
    "details": {}
  }
}
```

### Prompting

#### Draft query generation prompt

```markdown
{SYSTEM_PROMPT}

{cleaned up version of the user's prompt}.  

This is a query that a user has for our DB.

{tables + columns from Glue}

Here are some example requests from users and the correct SQL queries for those requests:

"I want all posts by Stanley in the past month" -> "SELECT * FROM posts WHERE handle LIKE "Stanley" AND created_at > {past month}"

{example requests + SQL queries}

Given that we have these columns and tables, generate an Athena SQL query for this user's request.

{cleaned up version of the user's prompt}
```

#### Draft router prompt

```markdown
You are a routing agent, charged with gatekeeping access to a database.

Our database has the following tables and columns:

{tables + columns from Glue}

{other system prompt details}

This is a query that a user has for our DB.

{cleaned up version of the user's prompt}.  

This is a request that a user has for our DB.

Classify the request using the following labels:

- VALID
- INVALID_MISSING_DATASET: Invalid because we don't have that table/dataset.
- INVALID_MISSING_ROWS: Invalid because we lack the rows of data.
- INVALID_UNQUERYABLE_REQUEST: Invalid because the user request isn't something that can be queried (e.g., "What is 2+2").
- INVALID_OTHER: Invalid for other reasons.

{Include few-shot examples}

Classify the request:

{cleaned up version of the user's prompt}
```

#### Testing + Experimentation

We'll need to do some experiments and have eval datasets to see if we're generating the right prompts. We'll want to create 40-50 queries for each use case, determine common query patterns, and use a subset as representative few-shot examples while keep the remaining as a validation set.

We'll also add regression testing as part of nightly tests, CI/CD (especially before big production releases relating to the search functionality).

We also want to add telemetry and take a subset of production traffic, perhaps every 1-2 days, and manually QA the samples + generate new evaluation samples.

### Adding limits by default

The system should add conservative limits by default rather than relying on users to constrain their requests correctly.

These limits serve two purposes:

1. Prevent unexpectedly expensive Athena queries.
2. Prevent the system from returning datasets that are too large for the user or application to handle safely.

Initial limits should be configuration-driven rather than hard-coded.

Potential defaults include:

1. Maximum natural-language query length.
2. Maximum date range.
3. Maximum number of result rows.
4. Maximum estimated Athena bytes scanned.
5. Maximum result-file size.
6. Maximum query runtime.
7. Maximum number or complexity of joins.
8. Maximum daily requests or scanned bytes per user or project.
9. Maximum retry count per pipeline stage.

The SQL generation prompt should instruct the model to include defensive defaults, such as:

- Selecting only relevant columns rather than using SELECT *.
- Adding a bounded date range when the request permits it.
- Adding a result limit for exploratory requests.
- Avoiding unnecessary joins.
- Using partition columns where available.

### Gating on the `EXPLAIN ANALYZE` query

Our goal is to avoid naively running expensive queries. Our end users won't have the insight to know how expensive queries are to run, so we must make defensive design a core part of our plan.

Athena costs $5/TB to run. Even just $1 means scanning 200GB of records. We will use indexing and precomputed views (both out of scope of this design, will be more scoped out in [this proposal](https://github.com/METResearchGroup/lab_data_integrations_interface/issues/115)) as well as other optimizations to reduce the query scan cost, but if a query is costing even $1 to run, that's already a cause for caution for our current estimated scale.

As a first pass, we restrict queries scanning >10GB of data. As part of the beta phase of this application, we can restrict the amount of records that a user can access. 10GB is towards the upper limit of how many records a single nontechnical user can download on their computer (much less download in-memory into an R script or Jupyter notebook). Even if, say, only 10% of the scanned data is actually exported, 1GB is still a decently large dataset for a nontechnical user to manage on their personal laptop.

Given that this is how the majority of nontechnical users will likely interact with our interface, we can set this cap. We have limitations that should circumvent this (see the ##adding-limits-by-default section). We can direct users to contact the research team and we can collaborate with them to run larger queries. This will also allow us to work more closely with power users, troubleshoot queries that could be particularly tricky and/or costly, and simplify our development by removing a surface area for scalability problems during V1 development (costly/large-scale queries).

### Validation rules

#### Router layer validation

Let's treat any `INVALID_*` labels as hard failures and automatically invalidate the query.

We will also do testing (accumulating an eval set and refining the LLM prompt against it). We'll also review rejection decisions during beta testing to calibrate the LLM's propensity of assigning `INVALID_*` labels.

#### Validating generated SQL queries

We want to make sure that queries are read-only.

- We can allowlist read statements (e.g., `SELECT`, `WITH ... SELECT`) and restrict all other SQL queries.
- We also can require that queries be condensed to single statements, to avoid the possibility of 1 statement being a valid SQL query and another being invalid.

Stretch goal: we can ask a validator LLM if the SQL query would be a valid query to answer the user's request. For a V1, this is likely a stretch goal because it adds another LLM call and we should first see if this problem comes up before we prematurely add another LLM call per query (adding both cost and latency).

On invalid queries, for whatever reason it is deemed invalid, we can add the error message (or, in the case of the LLM validator, the reason why it's invalid) and retry the SQL query generation LLM call (up to n=3 times) using exponential backoff. Upon failing the last retry, we can hard-fail and log the error in our telemetry collector, returning a "Your request failed to be processed" message to the user.

#### Post-Athena validation/postprocesisng

We can do the following as postprocessing/validation steps once the Athena query results are completed:

- PII/column allowlist: this is a use case that hasn't come up yet but perhaps may come up depending on, for example, IRB requirements around exposing names of user handles.
- Empty results: return a "No results found" to the user.
- Error (Athena query couldn't complete): retry up to n=3 times. Upon failing the last retry, we can hard-fail and log the error in our telemetry collector, returning a "Your request failed to be processed" message to the user. We can be more specific if/when we see specific Athena errors.

Stretch goal: Review the returned columns (and perhaps the first 5 rows) and run an LLM query to see if, given this subset, the results likely captured what the user intended. If not, we can ask the LLM for a reason and then we can retry. This one is optional as it adds another LLM call to the pipeline. We should first evaluate if this is a real error case (e.g., by seeing actual queries whose results were not entailed by the request).

### Caching design

We want to invest in a good caching system (Redis cache + DB search of past queries + RAG) so as to avoid expensive queries + Athena calls. We also want to prioritize caching results of large queries, and caching results of smaller queries is less important (though will have to see financial tradeoff of keeping extra RAM in Redis + RAG queries vs. cost of executing smaller queries).

Our motivating example is the following user query:

```json
{
     "user_query": "I want all posts liked by Stanley in the past 2 months.",
     "cleaned_query": "i want all posts liked by stanley in the past 2 months",
}
```

#### Option 1: Matching on other entities or values

We can match on entities/values extracted from the user query.

```json
{
    "user_query": "I want all posts liked by Stanley in the past 2 months.",
    "cleaned_query": "i want all posts liked by stanley in the past 2 months",
    // don't match on the exact query string, match on the entities
    "users_referenced": "Stanley",
    "entities_mentioned": "posts",
    "timeframe": "last 2 months",
    // cache key could be something like {users referenced}::{entities}::{timeframe}
    // i want all posts liked by stanley in the past 2 months" vs.
    // i want all posts in the past 2 months  liked by stanley" have the same cache key
}
```

This is a low-cost approach, easy to implement and requires 0 LLM calls. The only inference cost may be from deploying NER models, but these are multiple orders of magnitude smaller than LLMs and easily fit in-memory.

#### Option 2: Fuzzy matching

Basically an extension of option 1, but not looking for exact match, but rather approximate string.

#### Option 3: Hybrid RAG (semantic search + BM25)

Can use RAG to find queries that are similar enough, then grab those similar queries, pass to an LLM,
ask an LLM "are any of these past queries the same as what a user is looking for?". If yes, return
the presigned URL for that past query.

Can possibly use a combination, e.g., using Option 1 first, then Option 2, then Option 3, in sequence.

Also Options 1+2 are probably via Redis, Option 3 is via vector DB (higher latency, higher cost, but more accurate)

#### Erring towards RAG rather than Redis

Although we keep the option of having a Redis cache layer in consideration, we don't expect requests to actually be repeated very often in practice. Caching is particularly valuable when equivalent requests occur repeatedly and remain valid for a useful period. However, it's likely that, for the use case of academic researchers, their requests will be so specific to their use case that once they get the data, they themselves won't make that same request again and it's unlikely that someone else will make a similar request.

Therefore, we can err on the side of using RAG retrieval to fetch semantically similar requests, if they exist, rather than using a Redis cache.

### LLM application deployment to production

The LLM application is more than just a model and prompt. A production LLM pipeline contains components such as:

- Model provider, identifier, and parameters.
- Prompt templates.
- Few-shot examples.
- Structured-output schemas.
- Deterministic validators.
- Retry/fallback behavior.
- Postprocessing logic.
- Embedding models + indexes.

Changing any of these can affect correctness, latency, cost, or reliability.

#### Deploying LLM pipeline changes to production

Changes to the LLM pipeline should follow a progressive release process, proportional to the risk of the change.

Some low-risk changes include:

- Correcting prompt wording without changing the output schema.
- Adding telemetry metadata.
- Adding a deterministic validator that can only reject invalid output.

Some higher-risk changes include:

- Changing the router model or prompt.
- Changing the meaning of a router label.
- Changing the SQL generation model.
- Modifying few-shot examples.
- Updating validation restrictions.

We want to follow a series of steps for these changes. The following is the "end stage" deployment checklist; during rapid iteration, especially during alpha/beta testing, we can shortcut some of these.

##### 1. Define the proposed change and hypothesis

Each change should begin with a clear statement of what is being changed and why, such as "We believe Model B can reduce router false acceptances without increasing false rejections by more than an acceptable amount". The proposal should clearly state the component being changed, the expected benefit, the metrics expected to improve, metrics that must not regress, known risks, rollback criteria, and if the change is backwards compatible.

##### 2. Create an isolated candidate configuration

The candidate change should receive its own immutable configuration version rather than modifying the current production configuration in place. For example:

```yaml
pipeline_version: nl_search_2026_07_11_candidate_01

router:
  model: ...
  prompt_version: router_v4
  few_shot_version: router_examples_v3
  temperature: 0
  
sql_generation:
  model: ...
  prompt_version: sql_generation_v7
  few_shot_version: sql_examples_v5
  temperature: 0
  
validators:
  version: sql_validators_v3
```

This allows the candidate and baseline to run side by side and makes rollback a configuration change rather than an emergency code modification.

##### 3. Run deterministic tests

Before running LLM evals, the change should pass normal unit and integration testing with determistic checks.

##### 3. Run offline evals

The canddiate should run against the offline eval suite. We should compare the candidate with the current production baseline on measures such as correctness, critical failure modes, latency, token usage, estimated cost, and retry behavior. We should also block on hard violations (e.g., generating write queries, accepting prompt-injection attempts, etc).

We can define two classes of gates:

- Hard gates: candidates can't be deployed if they result in unsafe SQL, accept adversarial requests, etc.
- Soft gates: accuracy/precision measures slightly change, p95 latency is within a certain range, etc. These are ones in which we may not have an explicit hard gate, but we'll want to take a closer look.

##### 4. Test in a dev environment

The candidate should be deployed in dev and exposed to real simulated behavior, such as known requests, pressure, load, and such.

##### 5. Shadow mode

For larger changes, the candidate can run against production requests. Users are still served results from the production pipeline, but we can compare the results of the production pipeline against the candidate changes.

##### 6. Canary

After offline and shadow validation, a candidate change can receive a small percentage of production traffic. We evaluate in the same way as the shadow mode.

##### 7. Release to production

After passing increasing percentages of prod exposure, a change can be released to production.

#### Offline evals strategy

Offline evals allow us to assess a candidate LLM pipeline before it hits production.

We should maintain a separate eval suite for each of the following:

- Router classification
- SQL generation
- RAG retrieval
- End-to-end pipeline behavior.

We should maintain a few sets of examples:

- Few shot examples, included directly in the prompts. These shouldn't be used in evals.
- Dev set: used while iterating on changes. Repeated comparison against this set will lead us to optimize against it, so we still need another hold-out set.
- Hold-out eval set: reserved for offline evals before release.
- Regression set: contains important failure cases observed over time.
- Adversarial set: requests containing adversarial inputs (prompt-injection, invalid requests, requests that would result in expensive SQL queries, etc.).

### Observability/Telemetry

#### System Ops

We'll want to add telemetry across the entire request lifecycle:

- Request acceptance
- Cache
- Router
- SQL query generation
- Validation
- `EXPLAIN ANALYZE`
- Execute query
- Validation
- Return response

We'll want to add request-level tracing.

Some metrics to add include:

- Latency: p50/p95/p99 per stage + end-to-end.
- Error rate by refusal reason (e.g., `INVALID_*`) and by exception class (timeout, validation failure, Athena query failure, etc.)
- Cache: hit/miss by layer (Redis/RAG).

Later on, as we have more concurrency requirements, we might also consider measuring number of concurrent queries.

Some of the core questions we care about include:

1. Did the overall request complete successfully?
2. Did each component perform within its operational targets?
3. If the request failed or degraded, can we quickly determine where and whhy?
4. Can the system protect itself from overload, expensive requests, failing dependencies, and other failures?
5. Can the team safely deploy, monitor, and recover the application?

We want to be able to both observe the end-to-end flow while also allowing us to isolate the behavior of each component separately.

##### General System Ops considerations

Some guiding principles we want to consider include:

1. **Observe both complete user journeys and individual services**: we want to be able to deep-dive into both end-to-end request flows as well as what happens in individual journeys.
2. **Define service-level indicators and objectives**: we want to have expectations for how the platform should perform.
3. **Measure both success AND quality of service**: a request that returns in 5 seconds versus a request that returns in 5 minutes both technically returned results, but are different in quality.
4. **Distinguish between requests rejected explicitly vs. requests that aren't fulfilled due to system error**: we want to make sure that we know when a request isn't fulfilled because, for example, it's invalid, as opposed to a request that isn't fulfilled because the pipeline breaks.

Additionally, some more general Ops-specific principles that we'll want to consider include:

1. Prefer structured telemetry over free-form logs, so we can more easily review later.
2. Avoid high-cardinality metrics: don't track things like "unique request IDs", as these are high cardinality metrics and we'll want to keep those in traces, not metric dimensions.
3. Use a single request identifier. We want to make sure that disparate artifacts (e.g., logs, traces, metrics, etc.) can be all linked through a common trace identifier. Every request should receive a unique `trace_id`.

A trace should be structured in a way that allows us to answer questions like:

1. Where did a slow request spend most of its time?
2. Did a request wait on an LLM step? The Athena query? Something else?
3. When we rejected a request, did we do it intentionally or did the request just fail?
4. How many times did a request retry?
5. Were we able to successfully fulfill a query but unable to deliver the result to the user?

##### Service-level indicators and objectives

We want to define SLIs/SLOs for our system. We can define some initial SLIs, and then after collecting traffic during beta development, we can develop SLOs.

Some initial SLIs to consider include:

- Request acceptance rate.
- Successful end-to-end completion rate.
- First-attempt success rate (also, retry rate).
- End-to-end latency.
- Time to produce the final result once a result is accepted.
- Percentage of accepted requests that fail before returning a result.
- Percentage of results/queries blocked by validation.

We should also carefully triage success/failure. One possible breakdown is something like:

- `SUCCESS_RESULTS_RETURNED`: the request completed and returned one or more records.
- `SUCCESS_NO_RESULTS`: the request completed correctly but matched no records.
- `REJECTED_ROUTER_REJECT`: the request was rejected by the router.
- `REJECTED_TOO_EXPENSIVE`: the query was too expensive.
- `FAILED_INTERNAL`: the request failed due to an application error.
- `FAILED_TIMEOUT`: the request failed a timeout.
- `FAILED_VALIDATION`: the request failed due to a validation step.

##### Latency/performance metrics

We should track end-to-end and per-stage latency at p50/p95/p99. in addition, we should also track performance using metrics such as: requests that complete on the first attempt, requests that require retries, cache hits vs. misses, and small/medium/large query performance.

##### Reliability

We can include explicit operational safeguards to promote reliability.

- Timeouts: each external call should have a bounded timeout.
- Retries: retries should be included for transient/retryable failures, using bounded exponential backoff with jitter.
- Circuit breaker: we want to temporarily stop calls to a dependency when repeated failures indicate that the dependency is unhealthy. For example, we should stop calling the router LLM node if it keeps returning an error, and automatically reject requests until the router is fixed (or some other reasonable fallback).

##### Logging

We can use structured logs, with a consistent schema across services.

Some fields we can add include: timestamp, log level, service, environment, application version, request ID, trace ID, span ID, pipeline stage, event type, outcome, duration, error code, retry attemp, etc.

##### Deployment and change management

Every trace and log should include the application version or Git commit so that any operational changes can be attributed to a deployment.

When we make changes, we should follow a progressive release process:

- Automated tests + integration tests
- Deployment to dev environment.
- Smoke tests against representative requests.
- Canary deployment.
- Full rollout.
- Rollback if needed.

##### Incident response and runbooks

We'll want to create runbooks for various foreseen incidents, such as per-stage failures.

Some of the things to include in a runbook are:

- How to identify the incident.
- Which dashboards and logs to inspect.
- Immediate mitigation steps.
- Fallback or degraded-mode behavior.
- Rollback procedures.
- How to identify affected requests.
- How to replay or recover failed requests.
- When and how to notify users or stakeholders.
- What information should be collected for a post-incident review.

##### Data retention and privacy

This is out-of-scope of the current plan. Right now we don't need pseudonymization.

#### LLMOps

For our use case, the LLM steps are relatively constrained (as opposed to free-form multi-agent or chatbot apps). However, they do fulfill core responsibilities in our pipeline, validating user requests and generating valid SQL. Our LLMOps strategy revolves around three pillars:

1. Was the LLM result correct?
2. Was the LLM behavior reliable, observable, and cost-efficient?
3. Can we audit and reconstruct how the result was produced?

##### General LLMOps considerations

Across all these pillars, there are a few principles for us to keep in mind.

1. **Evaluate each LLM task independently**: each LLM task has different assumptions, failure modes, and thresholds for failure, so we should evaluate each independently. They should each have their own evaluation datasets, metrics, and release thresholds.
2. **Optimizing for task-level correctness**: we want to avoid "shiny-object" syndrome and automatically plugging in the latest cutting-edge models. We want to prioritize designing LLM systems that perform well on their specific task. What this may mean, for example, is that a different LLM works better for the router than the RAG component.
3. **Utilize deterministic checks as much as possible**: We want to use deterministic verifiers and checks as much as possible, both to (1) complement LLM checks and (2) verify LLM results. For example, we can have a lightweight set of examples as well as edge cases (e.g., queries < 10 chars) to automatically filter some results before it gets to the LLM router. We can also use deterministic checks (see the "1. Was the LLM result correct?" discussion below) against the LLM-generated results. We want to avoid LLM-as-a-judge as much as possible, reserving it for more heavyweight, infrequent QA. An LLM should be able to propose an action (e.g., run a specific SQL query), but it should be gated and verified.
4. **Treat prompts, models, and configurations as versioned production artifacts**: Prompt templates, few-shot examples, model identifiers, inference parameters, schema context, and validators should be reviewed and deployed like code. We should define all of these as YAML configs and use a plugin-style architecture (see [this YAML config for an example](https://github.com/METResearchGroup/lab_data_integrations_interface/blob/main/data_platform/ingestion/configs/bluesky/default.yaml)). Not only should these be committed in Git, but we should, within reason, add these as trace-level metadata on production requests. At minimum, for each trace we should track the prompt, model, model parameters, and config version.
5. **Combine offline evals with online observation**: We discuss this more in the "LLM application deployment to production" section. A proper LLMOps strategy requires combining offline evals with online observations.
6. **Turn failures into regression tests**: As we track queries, we'll want to review meaningful production errors, incorrect refusals, expensive generated queries, and user-reported mistakes, and add them to the evaluation suite.
7. **Consider tradeoff between precision/recall on a case-by-case basis**: the tradeoff between recall and precision varies based on the LLM task. For the router LLM, for example, we would rather prioritize a high precision of the `VALID` label as any result that is marked as valid gets passed down to the next LLM caller to generate a SQL query. Too many incorrectly assigned `VALID` labels causes downstream callers to break.

##### 1. Was the LLM result correct?

We should define correctness separately per LLM module.

**Router correctness**: for router correctness, we want to know if the assigned label is correct. Therefore, we can make use of typical classification metrics:

- Overall accuracy/F1
- Class-specific precision/recall
- False acceptance rate: requests that should've been rejected but were passed to SQL generation.
- False rejection rate: valid user requests that were unnecessarily rejected.
- Confusion between the different `INVALID_*` labels.
- Performance on ambiguous, malformed, adversarial, and prompt-injection-like requests.

Not all errors are equal. As previously mentioned, false acceptance is particularly costly, while false rejections, albeit inconvenient to a user, is safer. During beta testing, we prefer that the router is conservative and requires tuning as opposed to a router that incorrectly accepts requests.

--

**SQL query generation correctness**: we can't do exact SQL string matching because multiple SQL statements can correctly answer the same requests. There's a few ways for us to evaluate SQL queries, ranging from syntax to correct data fetching:

- Is this SQL query valid, parseable, compilable SQL?
- Is the SQL query grounded in real tables/columns, or does it hallucinate?
- Is the SQL query read-only and single-statement?
- Can Athena successfully execute or explain the query?
- Does the query implement the filters, joins, aggregations, date ranges, ordering, and entities that are requestesd by the user?
- Does the query result in the correct data being fetched?

When designing the evaluation dataset, we'll want to include both common request template as well as difficult edge cases, such as:

- Similar entity/column names
- Multiple simultaneous filter
- Relative/absolute date ranges
- Joins
- Aggregated vs. raw-row retrieval
- Requests for unavailable or unsupported datasets.
- Ambiguous query references
- Queries that are logically valid but unreasonably expensive.

Where possible, we should verify SQL correctness against a stable fixtuer database or representative test tables. We'll want to complement SQL query correctness with comparing the results of the actual queries against the text fixtures.

--

**Cache/RAG correctness**: For using RAG to retrieve past queries, we want to prioritize precision, as we're OK with a user request being retried as opposed to being returned an incorrect past query whose result is then incorrect as well. We'll want to do a similar approach as the previous models, developing an evaluation set to evaluate RAG retrieval correctness (e.g., `precision@k`).

##### 2. Was the LLM behavior reliable, observable, and cost-efficient?

We also need to measure the operational behavior of the LLMs beyond accuracy. Some operational metrics that we'll want to consider include: p50/p95/p99, TTFT, input/output/total tokens, retry count, timeout rate, and rate limits. We'll want to consider this for each LLM step individually as well as at the level of the entire request.

We'll want to establish initial SLAs for each of these parameters.

##### 3. Can we audit and reconstruct how the result was produced?

For each LLM-derived result, we should be able to determine what inputs and configs produced it. We'll want values like: request/trace identifiers, timestamp, Git version commit, LLM model details (model name, hyperparameters), config/prompt version, etc.

Ideally, with sufficiently detailed audit trails, we can replay requests and understand why a particular result came to be. This is critical for reproducibility and debugging.

##### Tracking LLMOps in a dashboard

We'll want a dashboard (possibly an extension of [the dashboard created in this ticket](https://github.com/METResearchGroup/lab_data_integrations_interface/issues/113)) to track basic LLMOps metrics. We'll discuss later what metrics will be most important here (which will be informed by the approach the team agrees on in the aforementioned proposal ticket). Some initial thoughts: basic success/failure for each LLM step, snapshot count of LLM failure modes, p50/p95/p99 for each LLM step, cost for each LLM step.

#### FinOps

We want to be able to measure, control, and forecast the cost of operating the search system.

Our FinOps strategy revolves around 3 core questions:

1. Can we attribute cost to individual requests, features, and users?
2. Can we prevent unexpectedly expensive behavior before it occurs?
3. Can we forecast how cost changes as usage and data volume grow?

Our goal isn't to necessarily minimize infra spending. Instead, we want to know the total cost of serving a user request and to make cost-informed tradeoffs amongst the different components. For example, if we add a cache, the financial cost of that has to be considered against the benefits.

##### FinOps principles

We have a few FinOps principles core to the project scope:

- The key metric we care about is **what is the total cost of producing a valid result for a user?**
- Attribute cost as close to the request as possible.
- Proactively prevent cost where possible. For example, our `EXPLAIN ANALYZE` work is one way of preventig expensive queries.
- Separate fixed and variable costs.
- Evaluate cost alongside correctness and reliability.
- Treat budgets as operational guardrails.
- Make cost visible to engineers and product owners.

##### Cost model

We can use a simplified request-level model for tracking cost:

```markdown
total_request_cost =
    gateway_and_compute_cost
  + cache_cost
  + llm_inference_cost
  + athena_cost
  + storage_cost
  + data_transfer_cost
  + observability_cost
```

We make a distinction between costs associated with an individual request versus shared costs. Some direct variable costs include LLM input/output tokens, embedding generation, Athena bytes scanned, etc., while some shared costs include Redis memory ops and server compute.

Each request should include a `request_id`. Using this, we can link operational traces to cost-producing activities.

We can track mean/median cost per completed request, as well as p50/p90/p95/p99. We particularly care about tail costs as these are the ones most likely to exopnentially increase our total cost.

##### Controlling Athena costs

Athena is likely to be one of the largest cost centers, especially as the scale of queries increases. The system needs to proactively prevent unbounded scans through deterministic controls.

Some approaches to do this include:

- Pre-execution checks: table/column allowlists, maximum estimated bytes scanned, maximum date range, prohibition of certain joins, maximum output size, maximum result-row limit, per-user/per-project quotas, etc. This can complement the aforementioned work related to `EXPLAIN ANALYZE`.
- Runtime controls: we can enforce things like per-request execution timeouts, automated cancellation policies, etc.
- Post-execution monitoring: for every Athena execution, we can track estimated/actual bytes scanned, estimated/actual cost, query runtime, and result size. Large discrepancies between estimated/actual results should be reviewed.

Some common ways to reduce Athena costs include:

- Partitioning data by frequently filtered dimensions.
- Requiring partition files.
- Using compressed columnar formats (our pipeline already uses .parquet).
- Using precomputed views.
- Compacting small files.
- Using prior results.
- Avoiding repeated scans for pagination.

This implies a close collaboration with data platform work in order to make sure that the query patterns in the search interface match data platform and format assumptions.

##### Controlling LLM costs

LLM costs are the other most likely contributor to the cost of an individual request. LLM cost should be measured separately per caller. For each, we should track metrics such as input/output tokens and cost per call, in addition to other LLM fields (see the "LLMOps" section for more detail).

When we consider the cost for a model, we should review under a policy of cost-adjusted quality rather than cost alone. We will likely err towards using a distilled `*-nano` model, but we want to review the performance of such models against other larger models to see if any possible improvement is worth the increase in cost (we'll discuss this as a team after experimentation).

Some potential LLM cost controls to consider incldue:

- Maximum prompt-token, output-token budgets.
- Retrieving only relevant tables/columns.
- Limiting the number of few-shot examples.
- Varying usage of small/large models, erring towards using small models.
- Caching results aggressively.
- Using deterministic validators instead of LLM validators.

##### Controlling cache costs

Caching is most helpful when the underlying queries are expensive, requests are likely repeated, and results remain valid for a useful period.

We anticipate that requests won't be repeated that often. We instead can err towards using RAG retrieval to fetch similar requests, if any.

##### Controlling storage and result-retention costs

Large result files might become a meaningful storage cost over time. For each result artifact, we'll track: request identifier, size, expiration time, number of downloads, and associated query cost.

We also want to reference against a retention policy. This retention policy should account for user expectations, research reproducibility, IRB requirements, etc.

### Scaling how we manage query results

A v1 approach is presigned URLs. We can probably ship this as a v1, but what do we do with queries that will return LARGE results? A few options here:

- Disallow such queries, and tell them to contact the team: this removes the possibility of an end user querying lots of data, but still leaves it up to the internal team to have a policy for queries with a large number of results. This can possibly be combined with other methods (see below)
- Return paginated results: We can either (1) paginate the query internally, run multiple queries, and combine the results after the fact, or (2) run the expensive query once and then paginate the results ourselves. We can experiment with the more feasible approach (feasible via cost + runtime). I suspect the second approach is better since running multiple queries in order to get subsets of rows will result in more disk reads, which is where the cost will really pile on.

#### Guiding principles to consider

For scaling the results, there are a few principles for us to consider:

1. Execute expensive queries at most once: Pagination should not repeatedly scan the same Athena data.
2. Separate query execution from result consumption: Once a query is done, users should read or download the materialized artifact instead of re-executing the query.
3. Apply limits before execution where possible.
4. Treat large exports as async jobs: the HTTP request should not remain open while a large query and export completes.
5. Use different delivery paths for previews and full datasets: interactive pagination is useful for inspecting results, while a file export is more appropriate for complete datasets.
6. Reject workloads we can't safely support.

#### A tiered management policy

We can define configurable result tiers and have a separate management approach for each. We'll have to determine these thresholds based on beta usage and user research.

##### Small results

Small results can be materialized as a single file, stored in S3, and returned through a presigned URL. This is our default V1 path.

##### Medium results

Medium results are still safe to execute automatically, but may be inconvenient as a single uncompressed .csv. Some options here include:

- Compressing the output
- Splitting the output into multiple files
- Offering a small preview and then a complete download
- Using parquet instead of .csv
- Using a shorter or policy-based retention period.

We can likely combine multiple options into a single policy.

##### Large results

During V1 development, large results should be rejected and routed to the team for manual handling. Manual handling allows the team to learn what types of large requests users make before investing in a policy for handling large results. The team can also suggest refinements to the user's queries, like a narrower time range.

#### Proposed V1

For V1, we should:

1. Accept the natural-language request asynchronously.
2. Generate and validate the SQL query.
3. Estimate query cost and output size where possible.
4. Reject queries above the configured automatic-execution limits.
5. Execute accepted queries once.
6. Materialize the result to S3.
7. Generate a presigned URL.
8. Return or send the URL to the user.
9. Expire the result according to the retention policy.

We should support a small result preview, but we do not need full interactive pagination during V1.

This is appropriate because the expected user goal is to obtain a research dataset for use in R, Python, or another analysis environment. Pagination improves browser usability, but it does not solve the user’s need to retrieve the complete dataset.

#### Async job model

Even moderate Athena requests may take longer than is appropriate for a synchronous HTTP connection.

The API should model the request as a job with states such as:

- PENDING
- ROUTING
- GENERATING_SQL
- VALIDATING
- ESTIMATING_COST
- QUEUED
- EXECUTING
- POSTPROCESSING
- READY
- REJECTED
- FAILED
- EXPIRED

The initial API response can return a job identifier. The frontend can then poll a status endpoint or use another notification mechanism.

The completed job should include:

- Final status.
- Human-readable status message.
- Result metadata.
- Row count where available.
- Result size.
- File format.
- Expiration time.
- Presigned download URL.
- Error or rejection reason.

This also makes large-query execution more resilient to browser refreshes and network interruptions.

#### Materialized-result design

Each completed request should create a result artifact or a result manifest.

A result manifest may include:

```json
{
  "request_id": "...",
  "result_id": "...",
  "status": "READY",
  "format": "csv.gz",
  "row_count": 250000,
  "total_size_bytes": 125000000,
  "created_at": "...",
  "expires_at": "...",
  "files": [
    {
      "file_index": 0,
      "size_bytes": 64000000,
      "row_count": 128000,
      "storage_key": "..."
    },
    {
      "file_index": 1,
      "size_bytes": 61000000,
      "row_count": 122000,
      "storage_key": "..."
    }
  ]
}
```

The manifest allows us to:

- Split large exports into manageable chunks.
- Resume partial downloads.
- Generate separate presigned URLs.
- Track artifact size and retention.
- Validate that all chunks were generated.
- Avoid rerunning the query.

## Cross-cutting concerns

### Security and authorization

All access controls must be enforced service-side.

Some measures include:

- Authenticating every user.
- Ensuring generated SQL cannot bypass authorization.
- Restrict Athena to read-only workloads.
- Use short-lived presigned URLs.

### Idempoptency and duplicate requests

Submitting or retrying the same request should not unintentionally create multiple expensive Athena executions. The job creation endpoint should have an idempotency key or an equivalent request-deduplication mechanism.

The backend should distinguish between retrying an existing job, replaying a failed pipeline stage, intentionally submitting a new query, and reusing a previous completed result. Retries after Athena execution should reuse the existing query result whenever possible rather than rerunning the query.

### Configuration and environment management

Limits, prompts,  models, and as much of the infra setup as possible should be configuration-driven. Configuration changes should be versioned and included in request traces.

In addition, we should have two environments, `dev` and `prod`, each with their own setup.

### Failure isolation and degraded behavior

Failures in one optional component should not necessarily make the entire application unavailable. Each dependency should have explicit timeout, retry, fallback, and circuit-breaker behavior.

### Consistency and state transitions

The asynchronous job state should have a single authoritative store.

State transitions should be atomic and validated. For example:

- A READY job should always have a valid result artifact.
- A FAILED or REJECTED job should contain a stable reason.
- An expired result should no longer expose an active download URL.
- Reprocessing should not overwrite a completed result without an explicit new version.

The database record, S3 artifact, and user-visible job status should not silently disagree.

### User experience and explainability

The system should communicate clearly when a request is:

- Accepted and still running.
- Rejected as unsupported.
- Too large or expensive.
- Valid but returns no results.
- Failed due to a temporary system error.
- Ready for download.
- Expired.

Users should receive actionable guidance rather than internal error details. For example, a large request should suggest narrowing the date range or selecting fewer fields.

The system may show a brief normalized interpretation of the request so that the user can identify obvious misunderstandings before downloading the result.

### Maintainability and ownership

Logical responsibilities should remain separated even if V1 is deployed as a single backend service.

We should maintain clear ownership boundaries for:

- Frontend.
- API and job orchestration.
- LLM pipeline.
- SQL validation and query policy.
- Athena and data platform.
- Result artifacts.
- Observability.
- Cost governance.

This allows individual components to evolve independently and avoids turning the backend into a single tightly coupled request handler.

## Errata

*A design doc is essentially the same thing as an RFC. Some companies, like Uber, call it RFCs, while others, like Google, call it Design Docs.

Some resources:

- [Practical Engineer article on RFCs](https://blog.pragmaticengineer.com/scaling-engineering-teams-via-writing-things-down-rfcs/)
- ["How we use RFCs"](https://resend.com/handbook/engineering/how-we-use-rfcs)
- [Design docs at Google](https://www.industrialempathy.com/posts/design-docs-at-google/)

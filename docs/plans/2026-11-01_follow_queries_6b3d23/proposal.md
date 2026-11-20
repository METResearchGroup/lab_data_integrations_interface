# Proposal: Query recorded follow targets by DID

Scope: Add one follow lookup to the existing query graph. This proposal covers the query contract, affected files, output, and decisions. It excludes ingestion changes and current follow-state reconstruction.

## Overview

A user can ask for the accounts followed by an explicit DID. The graph selects the existing `follows` table and returns distinct `subject_did` values for that actor. The result describes recorded follow targets, not a complete or current following list.

## Cross-cutting concerns

### Data and meaning

`bluesky_ingestion_jetstream/schemas/arrow_schemas.py` already registers `FOLLOW_SCHEMA` in `RECORD_TYPE_TO_SCHEMA`. Its `did` field identifies the actor, and `subject_did` identifies the account followed. `bluesky_ingestion_jetstream/event_parsing/follows.py` reads the target from the record's `subject` field.

`bluesky_ingestion_jetstream/network/connection.py` accepts create operations and ignores deletes. Stored records cannot establish whether a follow is still active, and database coverage may be incomplete. The result email must say this. A current following list requires another source or deletion reconciliation.

### Reuse and limits

`backend/agentic_search/graph/graph.py` already connects validation, generation, postprocessing, and execution. `build_snapshot` in `query_validation/orchestrator.py` already includes the follow schema. The missing capability is an actor DID predicate, so no new graph or query framework is proposed.

The existing `resolve_dates` assigns an eight-calendar-day window to an undated request. For this lookup, an undated request should instead cover all stored follow records. Explicit dates filter follow record `created_at`. The existing 10 GiB estimated scan cap in `query_postprocessing/check_scan_cost.py` remains in place. A full-history request that exceeds it is rejected with the existing request to narrow the dates.

The scan estimator must count the actor DID column as well as the selected target column. It should not assume that a DID filter prunes Iceberg files unless the metadata supports that conclusion. The existing Athena execution and 24-hour CSV link are reused. No new dependency or storage location is proposed.

## File structure

### Repository

```text
backend/agentic_search/
  query_validation/
    models.py                         add follow-specific validation issues
    orchestrator.py                   validate the supported follow lookup
    query_intent/
      models.py                       add the actor DID to QueryIntent
      prompts.py                      extract lookup direction and actor DID
      extract.py                      preserve undated follow lookup bounds
      dates.py                        support that narrowly scoped date behavior
  query_generation/
    generate.py                       create the follow SELECT and DID predicate
  query_postprocessing/
    check_scan_cost.py                count the DID predicate column
  handle_query.py                     add the recorded-follow limitation to the email
  smoke_tests/                        exercise the new path and post-query regression
```

These are proposed changes to existing files. No production module, table, graph node, or storage destination is added. The ingestion code, table schemas, UI, deployment, and existing post-query behavior stay unchanged.

### Storage outside the repository

Athena continues to write its result CSV to the existing workgroup output location. `query_execution/execute.py` continues to create a link to that file. The proposal adds no new S3 prefix or persisted model.

## Schema and key interfaces

| Model or interface | Lives in | Role |
| --- | --- | --- |
| `QueryIntent` | `backend/agentic_search/query_validation/query_intent/models.py` | Existing in-memory structured extraction result. Add `actor_did: str \| None = None` and `follow_lookup: Literal["targets_by_actor", "unsupported"] \| None = None`. For the supported lookup, `record_type` is `FOLLOWS`, `columns` is `["subject_did"]`, and `actor_did` is the single requested actor. Existing date and inferred-date fields retain their roles. |
| `ValidationResult` and `ValidationIssue` | `backend/agentic_search/query_validation/models.py` | Existing in-memory result and issue enum. Add issue values for missing, invalid, or unsupported follow lookup input. No DID is sent to SQL unless validation accepts it. |
| `generate_sql(intent: QueryIntent) -> GeneratedQuery` | `backend/agentic_search/query_generation/generate.py` | Existing interface. For this lookup, generate `SELECT DISTINCT subject_did` from `bluesky_raw.follows`, filter `did` with the validated actor and exclude null targets. Use `_sql_string` for the value and fixed identifiers. |
| `estimate_scan_bytes(table: Table, intent: QueryIntent) -> int` | `backend/agentic_search/query_postprocessing/check_scan_cost.py` | Existing interface. Include both `did` and `subject_did` when estimating the lookup. Keep the existing date pruning and file-size fallback. |
| `handle_query(query: str, email: str) -> None` | `backend/agentic_search/handle_query.py` | Existing interface. Add a note to successful follow results explaining that they are recorded targets and may include unfollows or omit records. |

The actor DID and lookup type are inputs to the in-memory intent. The explicit lookup type lets validation reject unsupported follow questions rather than treating an absent DID as a general query. The CSV stores distinct target DIDs only. The existing query result objects and email delivery remain in use.

The lookup accepts one explicit DID and rejects missing, malformed, ambiguous, or unsupported follow requests. It does not resolve handles, query followers, join profiles, or traverse the graph. A follow lookup without dates has no date predicate. A lookup with dates applies the existing inclusive UTC date semantics to `created_at`.

For illustration, the intended query shape is:

```sql
SELECT DISTINCT subject_did
FROM bluesky_raw.follows
WHERE did = 'did:plc:example' AND subject_did IS NOT NULL
```

The DID is an example. If ordering is included, it must be valid for a distinct selection and must not require an unselected `created_at` expression.

## Steps

### Step 1: Extract and validate the follow lookup

Extend `QueryIntent` and its prompt for one actor DID and the direction requested. Keep an undated follow lookup unbounded by date, while preserving existing date behavior for other queries.

### Step 2: Generate and assess the query

Extend `generate_sql` with the fixed follow lookup shape. Extend `estimate_scan_bytes` to count the predicate column and retain the existing scan cap and SELECT-only check.

### Step 3: Describe the result

Add the recorded-follow limitation to the result email and retain the existing CSV delivery. Check that other query types keep their current output and behavior.

## Expected results

An accepted request produces a CSV with one `subject_did` per distinct recorded target for the requested actor. A request above the scan cap is rejected before Athena execution. No runtime, result count, or cost has been measured for this lookup.

## Decisions to confirm

1. **Result meaning.** Recommend a labelled list of recorded follow targets for v1 because the existing table stores creates but does not reconcile unfollows. The alternative is to defer the feature until a source of current relationships is available.
2. **Undated requests.** Recommend searching all stored dates, subject to the existing scan cap, because the user asks for all accounts. The alternative is to require a date range, which reduces scan cost but changes the question's meaning.

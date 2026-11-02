# Query recorded follows by account DID

## Goal

Support a first query such as “give me all the accounts followed by user
`did:plc:example`” through the existing query graph. Return distinct target
DIDs from follow records available in the database. This is a proposal; it
does not change the application.

## What exists

- `bluesky_ingestion_jetstream/schemas/arrow_schemas.py` already includes
  `follows` in `RECORD_TYPE_TO_SCHEMA`. Its common `did` field is the actor
  and `subject_did` is the account followed. The parser reads the latter from
  the record's `subject` field.
- `backend/agentic_search/query_validation/orchestrator.py` includes that
  schema in the catalog given to intent extraction. The graph already routes
  validated intents through SQL generation, scan estimation, Athena, and a
  CSV download link. Adding the schema alone will not add an actor filter:
  `QueryIntent` has no DID predicate and the SQL generator does not use one.
- The existing date resolver supplies an eight-calendar-day window when no
  dates are specified. Applying it to the example would silently omit older
  records. The 10 GiB estimated scan limit still applies.
- The Jetstream connection accepts create operations and ignores deletes.
  The stored follow rows therefore do not establish that an account is still
  followed. Ingestion coverage may also be incomplete. Do not present this
  result as a complete or current Bluesky following list.

## Proposed v1

1. Extend the existing structured intent with an optional actor DID. Teach
   its prompt that “accounts followed by X” selects `follows`, filters
   `did` by X, and returns `subject_did`. Require exactly one explicit DID
   for this v1 shape. Reject a missing, invalid, or ambiguous DID; do not
   guess a handle or execute an unfiltered query.
2. For this follow lookup only, do not infer the default date window when
   the user gives no dates. Preserve explicit dates and the existing date
   behavior for all other queries. A full-history lookup may exceed the scan
   cap; report the existing rejection and ask for a narrower date range.
3. Extend the existing deterministic SQL generator to select distinct
   `subject_did` values from `bluesky_raw.follows` with an exact `did`
   equality predicate, excluding null targets. Escape the DID as an Athena
   string literal using the existing helper. Keep user input out of table and
   column identifiers. An explicit date range applies to follow-record
   `created_at`, not to the date of a verified current relationship.
4. Update the existing scan estimator to include the `did` filter column
   even though the output selects only `subject_did`. Keep its estimate
   conservative: do not assume the DID predicate prunes files unless Iceberg
   metadata proves that it does. Retain the 10 GiB cap and select-only check.
5. Reuse the existing Athena execution and email/CSV path. Label the output
   as recorded follow targets, with a clear warning that deletes and complete
   coverage are not established. Preserve the current 24-hour link expiry.

The logical query for an undated request is:

```sql
SELECT DISTINCT subject_did
FROM bluesky_raw.follows
WHERE did = 'did:plc:example' AND subject_did IS NOT NULL
```

The DID above is illustrative. The exact generated SQL may include ordering;
it must not introduce a date predicate for this undated lookup. If ordering
is retained with `DISTINCT`, it must be valid Athena SQL and not require an
unselected `created_at` expression.

## Scope and guardrails

Change intent extraction and validation, date resolution for this lookup,
SQL generation, scan estimation, and result wording only where needed for
the flow above. Keep graph structure, ingestion, table schemas, deployment,
and existing post-query behavior unchanged. V1 does not resolve handles,
query followers, traverse graphs, join profiles, reconstruct deletions, or
claim a live following list. Reject unsupported follow requests rather than
silently broadening or reversing their direction.

## Verification before release

- Smoke-check extraction and SQL for the example, including exact actor/target
  direction, `DISTINCT`, and no inferred dates. Check explicit dates, missing
  or malformed DID, quotes in input, and unsupported reverse-direction asks.
- Check that the estimate counts both `did` and `subject_did`, and rejects a
  scan above the existing cap without submitting it to Athena.
- Run the repository lint and existing test checks, plus regression smoke
  checks for post queries and their default date behavior.
- With an approved, bounded Athena query and a known account, compare returned
  DIDs with the stored follow rows. Check the email's limitation and CSV link.
  This verifies the data path, not the completeness or current state of the
  account's Bluesky follows. Do not release until the wording is acceptable.

## Decision for review

Is a clearly labelled list of **recorded follow targets** sufficient for v1?
If the requirement is the account's current following list, a source that
reconciles unfollows and coverage is needed before making that claim.

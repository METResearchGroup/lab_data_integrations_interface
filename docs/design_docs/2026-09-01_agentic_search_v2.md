<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [Background](#background)
- [New Components](#new-components)
  - [API Gateway](#api-gateway)
    - [Rate limits](#rate-limits)
  - [SQL Query postprocessing](#sql-query-postprocessing)
    - [SELECT queries only](#select-queries-only)
    - [EXPLAIN ANALYZE](#explain-analyze)
- [Implementation Plan](#implementation-plan)
- [Out of Scope](#out-of-scope)
- [Open Questions](#open-questions)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# Background
Currently we have a V1 agentic querying system set up, but we want to expand this into a V2, 
which will have a few more hardening components. 

# New Components

https://www.tldraw.com/f/iM1LSt5r_UGp_P1T36U1j?d=v-1194.-431.3692.2427.page
(new nodes highlighted)

1. API Gateway 

2. SQL Query postprocessing
- Only SELECT queries allowed
- Run EXPLAIN ANALYZE to make sure query is under certain $ amount

## API Gateway

### Rate limits
We don't want people to be able to spam our query system with too many requests at once.

## SQL Query postprocessing

### SELECT queries only
If someone tries to update or delete or add new data to our database, we need to strictly forbid this. 

### EXPLAIN ANALYZE
Currently, we set a LIMIT on the amount of rows people can gather. This doesn't make the SQL query cheaper, it just 
filters out rows that it already queried. EXPLAIN ANALYZE will make sure that our queries run under a certain $ amount, 
as it tells us how much a query is going to cost before we actually run the query. With this, we'll implicitly set a limit by running EXPLAIN ANALYZE instead of setting a LIMIT on the returned rows. 

# Implementation Plan

There are two lines of work which can be done in parallel and are independent of each other

1. Implement rate limits. This should not be coupled to running the acutal query, so
we'll keep it out of the LangGraph app. 
2. Add another node in the LangGraph app for query postprocessing.

# Out of Scope
A design choice that we were considering was keeping the validation part of the async work vs 
having it return validation result to the user. i.e, if the user's request is invalid, we currently
send it to them via the email, instead of returning a response in the UI directly. 

The pros and cons for returning a response in the UI directly:
**Pros**: 
- better UX
**Cons**: 
- Need to keep longer persistent connection/deal with network failures
- Would have to move around the already-working app
**How it would be implemented**: 
- Remove query checks from LangGraph
- If query is valid, then run the LangGraph, else return response saying invalid

For now, unless users specify that they would really like the change, we'll just keep what's working for now. 

# Open Questions
1. For API Gateway, anything other than rate limits at the moment?
2. What should rate limits be for queries? Once a minute? Once every x seconds?

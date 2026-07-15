<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [ADR 1: Past Post URI Lookups for Dedupes](#adr-1-past-post-uri-lookups-for-dedupes)
  - [Context and Problem Statement](#context-and-problem-statement)
  - [Decision Drivers](#decision-drivers)
  - [Considered Options](#considered-options)
  - [Decision Outcome](#decision-outcome)
  - [Pros and Cons of the Options](#pros-and-cons-of-the-options)
    - [Option A: S3 + Sqlite](#option-a-s3--sqlite)
    - [Option B: DynamoDB](#option-b-dynamodb)
    - [Option C: S3 + Athena](#option-c-s3--athena)
    - [Option D: S3 + DuckDB](#option-d-s3--duckdb)
  - [Validation](#validation)
  - [Consequences](#consequences)
  - [References](#references)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# ADR 1: Past Post URI Lookups for Dedupes

- **Status**: Accepted 
- **Date**: 2026-06-15
- **Deciders**: Stanley Du, Mark Torres

## Context and Problem Statement

We want to be able to filter out already processed posts before ingestion happens.


## Decision Drivers

- Keep infrastructure and compute costs low
- Architecture should scale
- Latency isn't too as important as first two factors, performance is a plus


## Considered Options

- Option A: S3 + Sqlite 
- Option B: DynamoDB
- Option C: S3 + Athena
- Option D: S3 + DuckDB

## Decision Outcome

- **Chosen option**: Option C: S3 + Athena
- **Why**: Low infrastucture costs and scales very well.

## Pros and Cons of the Options

### Option A: S3 + Sqlite

- **Pros**
  - Cheap
  - Simple to implement, least change to codebase
- **Cons**
  - Doesn't scale well

### Option B: DynamoDB

- **Pros**
  - Serverless
  - Quick at small batch sizes (amount of posts being checked for dupes)

- **Cons**
  - By far the most expensive
  - Slower for larger batch sizes 

### Option C: S3 + Athena

- **Pros**
  - Cheap
  - Scales well
  - Serverless
- **Cons**
  - Larger changes to existing codebase

### Option D: S3 + DuckDB

- **Pros**
  - Cheap
  - High performance across small to medium scale
- **Cons**
  - Harder to scale past a few million posts

## Validation

Performance testing + Cost Analysis at the PR:
https://github.com/METResearchGroup/lab_data_integrations_interface/pull/72

## Consequences

- **Positive**
  - Will be able to cheaply and quickly check for duplicate post ID's
  - This is easy to scale past millions of post ID's
- **Negative / Risks**
  - Breaking something in codebase due to significant logic changes to deduping logic
  - Need to manage new S3 files "section," S3 is no longer just post-data pipeline files

## References
- https://github.com/METResearchGroup/lab_data_integrations_interface/issues/71
- https://github.com/METResearchGroup/lab_data_integrations_interface/pull/72
<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [Background](#background)
- [Proposal](#proposal)
- [Implementation Plan](#implementation-plan)
  - [Ingestion](#ingestion)
    - [Receive Data from Websocket](#receive-data-from-websocket)
    - [Periodically Flush to S3](#periodically-flush-to-s3)
    - [Update cursor in DynamoDB](#update-cursor-in-dynamodb)
    - [Ingestion pipeline](#ingestion-pipeline)
    - [Buffer max capacity](#buffer-max-capacity)
    - [Clearing the buffer/uploading to S3](#clearing-the-bufferuploading-to-s3)
  - [Splitting Data into Individual Tables](#splitting-data-into-individual-tables)
    - [Filter the Data](#filter-the-data)
    - [Upload Filtered Data to S3](#upload-filtered-data-to-s3)
    - [Update Partitions](#update-partitions)
    - [Decision: Use Partition Projection](#decision-use-partition-projection)
    - [Proposed S3 Layout for Partition Projection](#proposed-s3-layout-for-partition-projection)
  - [Open Questions:](#open-questions)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# Background

In the current data platform we specify a particular way to retrieve records from Bluesky. We use the direct Bluesky API. We then also get only posts currently. We take this and pass it into the rest of the pipeline. We want to expand to more methods of ingestion from Bluesky as well as more data types.

# Proposal

Use the Bluesky Jetstream API to access all data from a few days up to a few weeks ago. Since the Jetstream is a continuous WebSocket connection, we will always try to keep connected to the WebSocket, and keep a cursor for when we lose the connection. 

# Implementation Plan

System design diagram:
https://www.tldraw.com/f/Pau4SS84LG1WNbbCmFuFm?d=v731.-104.648.426.page

## Ingestion

### Receive Data from Websocket

We should keep a websocket connection to the Jetstream and continuosly stream their data into our machine's memory. 
We should start receiving data from our cursor's value. 

### Periodically Flush to S3

We can do this in 2 ways:

1. Every x amount of time

2. After x amount of data enters our server

### Update cursor in DynamoDB

Because it is unrealistic to always keep our WebSocket connection, we need some way to know where to leave off.
We can do this by storing the cursor in DynamoDB so that when our connection goes down, we know where to restart.
We will update the cursor after all of our buffers have been flushed, so that the cursor never gets ahead of any event.

### Ingestion pipeline

```mermaid
flowchart LR
    A["1 WebSocket<br/>Connection"] --> B["process record based<br/>on type (post, repost,<br/>likes, follows)"]
    B -->|"when any<br/>buffer is full"| C["Flush all 4 buffers"]
    C --> D["Update Cursor in<br/>DynamoDB"]
```

### Buffer max capacity
We want to flush all 4 buffers once any reach their capacity. However, some events are more likeley than others. 
Therefore, we will set a ratio of posts:likes:follows:reposts such that the amount of each event should be similar 
every time we flush each event the S3 table. 

### Clearing the buffer/uploading to S3
Use a retry + deadletter pattern for S3 uploads.

In addition, we should use a pandas dataframe to automatically split the data across dt/hr for us so that we can 
accurately place the data into their respective files. 

Provenance: We can consider adding in json files with run_id + created_at timestamps. 

## Splitting Data into Individual Tables

### Filter the Data
In general, we want a separate table for (platform, data_type) since each of these combinations potentially have different columns.

The reasoning is that:
1. We will have different columns for each of the data types, as well as each of the platforms.
2. Users likely will only query one platform at a time, so splitting platforms into separate tables makes sense. 

For example, with the platform Bluesky alone, we will have:
- Posts table
- Likes table
- Reposts table
- Follows table


### Upload Filtered Data to S3
We should have separate tables for each of these filters, and upload to S3 after we have received the data into memory.

### Update Partitions
3 Options:
1. Glue Crawler
- Cheaper than immediate Glue table updates, assuming we upload to S3 more frequently than we run Glue Crawler
- New data won't be queryable for x time

2. Immediate Glue Table updates
- New data is queryable immediately after update
- More expensive than Glue Crawler, assuming we upload to S3 more frequently than we run Glue Crawler

3. Partition Projection
- New data is queryable immedaitely after S3 upload
- Only works for highly predictable partition structures

### Decision: Use Partition Projection
How partition projection works:
You define all of the keys (and their data types) ahead of time
You define all of the values' ranges ahead of time
You'll never have to do glue table updates (save money!)

This works in our case since our paths should be very stable, rarely should we add new partitions. 
We can always need partitions if needed over time. 

### Proposed S3 Layout for Partition Projection
Instead, partition on flush time truncated to the hour, since that's the natural granularity of our periodic flush. Both the raw and filtered layouts key off the same `dt=`/`hour=` pair so cursor replay and backfills land in predictable locations:

```
s3://lab-data-integrations-interface/
├── bluesky/
│   ├── posts/               <-- Point Glue Table "bluesky_posts" here
│   │   └── stage=raw/dt=2026-07-16/run_123.parquet
│   └── follows/             <-- Point Glue Table "bluesky_follows" here
│       └── stage=raw/dt=2026-07-16/run_123.parquet
├── twitter/
│   ├── posts/               <-- Point Glue Table "twitter_posts" here
│   │   └── stage=raw/dt=2026-07-16/run_456.parquet
│   └── likes/               <-- Point Glue Table "twitter_likes" here
│       └── stage=raw/dt=2026-07-16/run_456.parquet
└── reddit/
    └── posts/               <-- Point Glue Table "reddit_posts" here
        └── stage=raw/dt=2026-07-16/run_789.parquet
```

Corresponding Glue table properties:
```
-- 1. Enable Projection
'projection.enabled' = 'true',

-- 2. Stage (Enum)
'projection.stage.type' = 'enum',
'projection.stage.values' = 'raw,preprocessed,features,curated',

-- 3. Date (Date type)
'projection.dt.type' = 'date',
'projection.dt.range' = '2025-01-01,NOW',
'projection.dt.format' = 'yyyy-MM-dd',

-- 4. Hour (Integer type with zero-padding)
'projection.hour.type' = 'integer',
'projection.hour.range' = '0,23',
'projection.hour.digits' = '2',

-- 5. The exact S3 path structure template (Notice platform and table are hardcoded)
'storage.location.template' = 's3://lab-data-integrations-interface/bluesky/posts/stage=${stage}/dt=${dt}/hour=${hour}/'
```

If we flush more/less often than hourly, `hour` could be dropped in favor of `dt` alone, or split further into `minute=` buckets — worth revisiting once we settle the flush interval from the open question below.

## Open Questions:
- How large should the buffer be? I think this depends on how much memory and cores our VM will have (potentially HPC)
- What should we use as the ratio for posts:follows:reposts:likes? https://bsky.jazco.dev/stats doesn't include reposts, 
is the reposts included in the posts? Either way, it is unclear just based off these stats

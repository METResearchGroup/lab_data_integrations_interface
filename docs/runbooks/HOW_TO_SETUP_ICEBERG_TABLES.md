# How to Set Up the Iceberg Tables

## Overview

This runbook covers creating the four Iceberg tables the Jetstream ingester writes to: `posts`, `likes`, `reposts`, and `follows`, in the Glue database `bluesky_raw`.

The split of ownership matters:

- **Terraform** ([`terraform/bluesky_ingestion_jetstream/main.tf`](../../terraform/bluesky_ingestion_jetstream/main.tf)) creates the S3 warehouse bucket and the Glue database — the containers.
- **[`bluesky_ingestion_jetstream/aws/bootstrap.py`](../../bluesky_ingestion_jetstream/aws/bootstrap.py)** creates the tables, by hand, once.

The tables are deliberately not Terraform resources: Iceberg rewrites a table's schema, partition spec, and snapshot pointer on every commit, which an `aws_glue_catalog_table` resource would read as drift and revert on the next apply.

The ingester itself never issues DDL. [`aws/catalog.py`](../../bluesky_ingestion_jetstream/aws/catalog.py) only loads tables and raises `MissingTablesError` if any are absent, so this bootstrap is a required step in any fresh environment.

---

## Prerequisites

- AWS credentials in the environment for **us-east-2**, with Glue (`CreateTable`, `GetTable`, `UpdateTable`) and S3 read/write on the warehouse bucket.
- Dependencies installed: `uv sync`.

---

## Step 1: Apply Terraform

From `terraform/bluesky_ingestion_jetstream/`:

```bash
terraform init
terraform apply
```

This creates the `lab-data-integrations-interface` bucket and the `bluesky_raw` Glue database. Skip if they already exist.

---

## Step 2: Run the bootstrap script

From the repo root:

```bash
uv run python -m bluesky_ingestion_jetstream.aws.bootstrap
```

Expected output on a fresh environment — one line per table, then the partition spec for each:

```
created bluesky_raw.posts -> s3://lab-data-integrations-interface/bluesky/raw/posts
created bluesky_raw.likes -> s3://lab-data-integrations-interface/bluesky/raw/likes
...
```

The script is idempotent. Tables that already exist print `exists` and are left untouched, so a partial failure is resolved by simply re-running.

Each table is created from its Arrow schema in [`schemas/arrow_schemas.py`](../../bluesky_ingestion_jetstream/schemas/arrow_schemas.py), rooted at its own S3 prefix, partitioned by `day(created_at)`, with the properties in [`aws/constants.py`](../../bluesky_ingestion_jetstream/aws/constants.py).

---

## Step 3: Verify

Re-run the bootstrap. All four tables should report `exists`:

```bash
uv run python -m bluesky_ingestion_jetstream.aws.bootstrap
```

Or ask Glue directly:

```bash
aws glue get-tables --database-name bluesky_raw --region us-east-2 \
    --query 'TableList[].Name'
```

Then start the ingester — it loads all four tables before the first event, so a catalog problem surfaces in the first second rather than at the first flush:

```bash
uv run python -m bluesky_ingestion_jetstream.main
```

---

## Changing a schema or table property later

Bootstrap **only creates**. It will not alter a table that already exists, and Iceberg stores table properties in metadata at creation time — so editing `TABLE_PROPERTIES` or an Arrow schema and re-running does nothing to live tables.

To actually change one:

- **Additive schema change** (new column): evolve it in place with PyIceberg's `update_schema()`, or via Athena `ALTER TABLE`. Do not drop and recreate.
- **Property change**: `ALTER TABLE ... SET TBLPROPERTIES` in Athena.
- **Incompatible change**: drop and recreate, which discards the data. Bootstrap deliberately does not offer a drop — doing it by hand is the point.

---

## Troubleshooting

**`RuntimeError: Glue database 'bluesky_raw' does not exist`**
Terraform has not run, or ran against a different account/region. Go back to Step 1.

**`MissingTablesError` when starting the ingester**
The database exists but tables do not. Run Step 2. The error names every missing table at once.

**`TableAlreadyExistsError` surfacing as a crash**
Bootstrap catches this per table, so it should not escape. If it does, the table exists in Glue but is not loadable as an Iceberg table — most likely a non-Iceberg Glue table sitting on the same name.

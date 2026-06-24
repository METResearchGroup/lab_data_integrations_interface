"""Create the bluesky_raw Glue table.

Run once from the repo root:

    PYTHONPATH=. uv run python data_platform/aws/setup_glue_tables_raw.py
"""

from __future__ import annotations

from data_platform.aws.athena import Athena
from data_platform.aws.constants import S3_BUCKET

_DDL = f"""
CREATE EXTERNAL TABLE IF NOT EXISTS bluesky_raw (
  uri            STRING,
  url            STRING,
  author_handle  STRING,
  text           STRING,
  created_at     STRING,
  like_count     BIGINT,
  repost_count   BIGINT,
  reply_count    BIGINT,
  quote_count    BIGINT
)
PARTITIONED BY (platform STRING, dataset_id STRING, run_dir STRING)
STORED AS PARQUET
LOCATION 's3://{S3_BUCKET}/raw/'
"""


def main() -> None:
    Athena().run_query(_DDL)
    print("created table: bluesky_raw")


if __name__ == "__main__":
    main()

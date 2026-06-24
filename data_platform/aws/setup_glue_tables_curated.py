"""Create the bluesky_curated Glue table.

Run once from the repo root:

    PYTHONPATH=. uv run python data_platform/aws/setup_glue_tables_curated.py
"""

from __future__ import annotations

from data_platform.aws.athena import Athena
from data_platform.aws.constants import S3_BUCKET

_DDL = f"""
CREATE EXTERNAL TABLE IF NOT EXISTS bluesky_curated (
  uri                       STRING,
  url                       STRING,
  author_handle             STRING,
  text                      STRING,
  created_at                STRING,
  like_count                BIGINT,
  repost_count              BIGINT,
  reply_count               BIGINT,
  quote_count               BIGINT,
  news_or_opinion_category  STRING,
  is_political              BOOLEAN,
  is_likely_spam            BOOLEAN,
  is_self_contained         BOOLEAN,
  is_structurally_complete  BOOLEAN,
  toxicity_prob             DOUBLE,
  toxicity_tier             STRING,
  political_stance          STRING
)
PARTITIONED BY (platform STRING, dataset_id STRING, run_dir STRING)
STORED AS PARQUET
LOCATION 's3://{S3_BUCKET}/curated/'
"""


def main() -> None:
    Athena().run_query(_DDL)
    print("created table: bluesky_curated")


if __name__ == "__main__":
    main()

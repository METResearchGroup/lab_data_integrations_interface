"""Create all bluesky feature Glue tables (one per feature).

Run once from the repo root:

    PYTHONPATH=. uv run python data_platform/aws/setup_glue_tables_features.py
"""

from __future__ import annotations

from data_platform.aws.athena import Athena
from data_platform.aws.constants import S3_BUCKET

_BASE = f"s3://{S3_BUCKET}/features/platform=bluesky/feature"

_DDLS: list[tuple[str, str]] = [
    (
        "bluesky_features_is_political",
        f"""
CREATE EXTERNAL TABLE IF NOT EXISTS bluesky_features_is_political (
  uri              STRING,
  label_timestamp  STRING,
  is_political     BOOLEAN
)
PARTITIONED BY (platform STRING, dataset_id STRING)
STORED AS PARQUET
LOCATION '{_BASE}=is_political/'
""",
    ),
    (
        "bluesky_features_is_news_or_opinion",
        f"""
CREATE EXTERNAL TABLE IF NOT EXISTS bluesky_features_is_news_or_opinion (
  uri              STRING,
  label_timestamp  STRING,
  category         STRING
)
PARTITIONED BY (platform STRING, dataset_id STRING)
STORED AS PARQUET
LOCATION '{_BASE}=is_news_or_opinion/'
""",
    ),
    (
        "bluesky_features_is_likely_spam",
        f"""
CREATE EXTERNAL TABLE IF NOT EXISTS bluesky_features_is_likely_spam (
  uri              STRING,
  label_timestamp  STRING,
  is_likely_spam   BOOLEAN
)
PARTITIONED BY (platform STRING, dataset_id STRING)
STORED AS PARQUET
LOCATION '{_BASE}=is_likely_spam/'
""",
    ),
    (
        "bluesky_features_is_self_contained",
        f"""
CREATE EXTERNAL TABLE IF NOT EXISTS bluesky_features_is_self_contained (
  uri                STRING,
  label_timestamp    STRING,
  is_self_contained  BOOLEAN
)
PARTITIONED BY (platform STRING, dataset_id STRING)
STORED AS PARQUET
LOCATION '{_BASE}=is_self_contained/'
""",
    ),
    (
        "bluesky_features_is_structurally_complete",
        f"""
CREATE EXTERNAL TABLE IF NOT EXISTS bluesky_features_is_structurally_complete (
  uri                       STRING,
  label_timestamp           STRING,
  is_structurally_complete  BOOLEAN
)
PARTITIONED BY (platform STRING, dataset_id STRING)
STORED AS PARQUET
LOCATION '{_BASE}=is_structurally_complete/'
""",
    ),
    (
        "bluesky_features_is_toxic_tiered",
        f"""
CREATE EXTERNAL TABLE IF NOT EXISTS bluesky_features_is_toxic_tiered (
  uri              STRING,
  label_timestamp  STRING,
  toxicity_prob    DOUBLE,
  toxicity_tier    STRING
)
PARTITIONED BY (platform STRING, dataset_id STRING)
STORED AS PARQUET
LOCATION '{_BASE}=is_toxic_tiered/'
""",
    ),
    (
        "bluesky_features_political_stance",
        f"""
CREATE EXTERNAL TABLE IF NOT EXISTS bluesky_features_political_stance (
  uri               STRING,
  label_timestamp   STRING,
  political_stance  STRING
)
PARTITIONED BY (platform STRING, dataset_id STRING)
STORED AS PARQUET
LOCATION '{_BASE}=political_stance/'
""",
    ),
]


def main() -> None:
    athena = Athena()
    for table_name, ddl in _DDLS:
        athena.run_query(ddl)
        print(f"created table: {table_name}")


if __name__ == "__main__":
    main()

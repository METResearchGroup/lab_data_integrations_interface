"""Count Bluesky posts per day from the Iceberg posts table.

Run from repo root:

    PYTHONPATH=. uv run python experiments/perspective_api_labeling_2026_08_11/get_post_count_by_day.py
"""

from __future__ import annotations

from data_platform.aws.athena import Athena

GLUE_DATABASE = "bluesky_raw"
# lab-data-integrations-interface workgroups may not exist in every AWS account;
# bluesky_raw_maintenance is created by terraform/bluesky_ingestion_jetstream.
WORKGROUP = "bluesky_raw_maintenance"
DAYS = ("2026-08-09", "2026-08-10")

QUERY = f"""
SELECT CAST(created_at AS DATE) AS created_at_day, COUNT(*) AS post_count
FROM posts
WHERE CAST(created_at AS DATE) IN ({", ".join(f"DATE '{day}'" for day in DAYS)})
GROUP BY CAST(created_at AS DATE)
ORDER BY 1
"""


def main() -> None:
    athena = Athena()
    execution_id = athena.run_query(
        QUERY,
        database=GLUE_DATABASE,
        workgroup=WORKGROUP,
    )
    rows = athena.fetch_rows(execution_id)

    print(f"database: {GLUE_DATABASE}")
    print(f"workgroup: {WORKGROUP}")
    print()
    print("created_at_day\tpost_count")
    for row in rows:
        print(f"{row['created_at_day']}\t{row['post_count']}")

    total = sum(int(row["post_count"]) for row in rows)
    print()
    print(f"total: {total}")


if __name__ == "__main__":
    main()

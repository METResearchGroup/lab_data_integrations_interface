from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd

from data_platform.utils.duckdb_features import feature_glob

# Columns selected from each feature CSV (excluding uri). Keys match FEATURE_REGISTRY.
FEATURE_WIDE_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "is_news_or_opinion": [("category", "news_or_opinion_category")],
    "is_political": [("is_political", "is_political")],
    "is_self_contained": [("is_self_contained", "is_self_contained")],
    "is_structurally_complete": [("is_structurally_complete", "is_structurally_complete")],
    "is_toxic_tiered": [
        ("toxicity_prob", "toxicity_prob"),
        ("toxicity_tier", "toxicity_tier"),
    ],
    "political_stance": [("political_stance", "political_stance")],
}


@dataclass(frozen=True)
class ConsolidateConfig:
    posts_csv: Path
    features_root: Path
    feature_names: tuple[str, ...] = tuple(FEATURE_WIDE_COLUMNS.keys())
    id_column: str = "uri"


def _feature_cte_sql(feature_name: str, glob_pattern: str, id_column: str) -> str:
    column_pairs = FEATURE_WIDE_COLUMNS[feature_name]
    inner_cols = ", ".join(
        f"{source} AS {alias}" if source != alias else source for source, alias in column_pairs
    )
    outer_cols = ", ".join(alias for _, alias in column_pairs)
    cte_name = f"feat_{feature_name}"
    return f"""
{cte_name} AS (
    SELECT {id_column}, {outer_cols}
    FROM (
        SELECT {id_column}, {inner_cols},
            ROW_NUMBER() OVER (PARTITION BY {id_column} ORDER BY {id_column}) AS rn
        FROM read_csv('{glob_pattern}', union_by_name = true)
    )
    WHERE rn = 1
)"""


def _build_consolidate_sql(config: ConsolidateConfig) -> str:
    id_column = config.id_column
    posts_path = config.posts_csv.as_posix()
    feature_ctes = [
        _feature_cte_sql(
            feature_name,
            feature_glob(config.features_root, feature_name),
            id_column,
        )
        for feature_name in config.feature_names
        if feature_name in FEATURE_WIDE_COLUMNS
    ]
    join_clauses = [
        f"LEFT JOIN feat_{feature_name} USING ({id_column})"
        for feature_name in config.feature_names
        if feature_name in FEATURE_WIDE_COLUMNS
    ]
    wide_cols = []
    for feature_name in config.feature_names:
        if feature_name not in FEATURE_WIDE_COLUMNS:
            continue
        for _, alias in FEATURE_WIDE_COLUMNS[feature_name]:
            wide_cols.append(f"feat_{feature_name}.{alias}")

    ctes_sql = ",\n".join(
        [f"posts AS (SELECT * FROM read_csv('{posts_path}', union_by_name = true))"] + feature_ctes
    )
    select_cols = ["posts.*"] + wide_cols
    return f"""
WITH {ctes_sql}
SELECT {", ".join(select_cols)}
FROM posts
{" ".join(join_clauses)}
"""


def build_wide_table(config: ConsolidateConfig) -> pd.DataFrame:
    """Join preprocessed posts with deduped feature label CSVs on uri."""
    sql = _build_consolidate_sql(config)
    conn = duckdb.connect()
    try:
        return conn.execute(sql).fetchdf()
    finally:
        conn.close()

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd

from data_platform.utils.duckdb_features import feature_glob


@dataclass(frozen=True)
class FeatureLabelQuery:
    """Query labeled record ids from feature CSVs across all feature runs."""

    features_root: Path
    id_column: str = "uri"

    def _feature_csv_glob(self, feature_name: str) -> str:
        return feature_glob(self.features_root, feature_name)

    def _feature_csv_paths(self, feature_name: str) -> list[Path]:
        return sorted(self.features_root.glob(f"*/{feature_name}.csv"))

    def labeled_ids(self, feature_name: str) -> set[str]:
        """Return ids labeled for feature_name in any features run directory."""
        if not self._feature_csv_paths(feature_name):
            return set()

        glob_pattern = self._feature_csv_glob(feature_name)
        conn = duckdb.connect()
        try:
            rows = conn.execute(
                f"""
                SELECT DISTINCT {self.id_column}
                FROM read_csv(?, union_by_name = true)
                """,
                [glob_pattern],
            ).fetchall()
        finally:
            conn.close()

        return {str(row[0]) for row in rows}

    def filter_unlabeled(
        self,
        records: pd.DataFrame,
        feature_name: str,
    ) -> pd.DataFrame:
        """Return records whose id is not yet labeled for feature_name."""
        if records.empty:
            return records.copy()

        labeled = self.labeled_ids(feature_name)
        if not labeled:
            return records.copy()

        mask = ~records[self.id_column].astype(str).isin(list(labeled))
        return records.loc[mask].reset_index(drop=True)

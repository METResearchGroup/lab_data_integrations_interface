from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd

from data_platform.utils.duckdb_features import flat_feature_csv


@dataclass(frozen=True)
class FeatureLabelQuery:
    """Query labeled record ids from flat feature CSVs at features root."""

    features_root: Path
    id_column: str = "uri"

    def _flat_feature_csv(self, feature_name: str) -> Path:
        return flat_feature_csv(self.features_root, feature_name)

    def labeled_ids(self, feature_name: str) -> set[str]:
        """Return ids labeled for feature_name in the flat feature CSV."""
        csv_path = self._flat_feature_csv(feature_name)
        if not csv_path.exists():
            return set()

        conn = duckdb.connect()
        try:
            rows = conn.execute(
                f"""
                SELECT DISTINCT {self.id_column}
                FROM read_csv(?, union_by_name = true)
                """,
                [csv_path.as_posix()],
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

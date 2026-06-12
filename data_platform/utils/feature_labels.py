from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from data_platform.utils.storage import StorageManager


@dataclass(frozen=True)
class FeatureLabelQuery:
    """Query labeled record ids from feature files at the features root."""

    feature_storage: StorageManager
    id_column: str = "uri"
    feature_csv_id_column: str = "uri"

    def labeled_ids(self, feature_name: str) -> set[str]:
        """Return ids labeled for feature_name in the feature file."""
        return self.feature_storage.load_seen_ids(
            self.feature_storage.root_dir,
            self.feature_csv_id_column,
            filename=self.feature_storage.filename_for(feature_name),
        )

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

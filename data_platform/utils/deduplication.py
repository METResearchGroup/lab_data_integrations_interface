import pandas as pd

from enum import StrEnum

class DedupePolicy(StrEnum):
    NONE = "none"
    CURRENT_RUN = "current_run"
    PRIOR_RUNS_SAME_DATASET = "prior_runs_same_dataset"
    PRIOR_RUNS_ALL_DATASETS = "prior_runs_all_datasets"

# NOTE: I'll have to think about how this is compatible with storage.py
# Do we want to expose this directly to callers or have it through
# storage.py? I'm leaning towards exposing it to callers (e.g., ingestion/sync_bluesky.py)
# but I'm open to changing it.

class DeduplicationManager:
    """Manages deduplicating records."""
    
    def __init__(self):
        pass

    # callers can use this as a generic way to get the unique
    # records.
    def load_previous_unique_records(self) -> set[str]:
        return set()

    def _load_seen_ids_same_dataset_across_runs(self) -> set[str]:
        return set()

    def _load_seen_ids_across_datasets(self) -> set[str]:
        return set()

    def _load_seen_ids(self, policy: DedupePolicy) -> set[str]:
        return set()

    def load_seen_ids(self, *policies: DedupePolicy) -> set[str]:
        seen_ids = set()
        for policy in policies:
            seen_ids.update(self._load_seen_ids(policy))
        return seen_ids
            

    # TODO: I need a better name, but this is the idea:
    # 1. Load once the set that you want to compare against.
    # 2. Use it at call sites as dedupe_df, dedupe_list, dedupe_set.
    def dedupe_df(
        self,
        df: pd.DataFrame,
        colname: str,
        set_to_compare_against: set[str]
    ):
        pass

    # TODO: needs a better name.
    def dedupe_set(self, set1: set, set2: set):
        pass
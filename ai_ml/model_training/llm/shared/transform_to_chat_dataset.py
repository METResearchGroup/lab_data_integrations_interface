"""Shared tools for transforming a series of labeled records into a chat-style dataset."""

from datasets import Dataset
import polars as pl

def _download_single_parquet_file_as_dataframe(s3_path: str) -> pl.DataFrame:
    return pl.read_parquet(s3_path)

def download_parquet_training_set(parquet_s3_paths: list[str]) -> pl.DataFrame:
    """Downloads the training dataset for the model."""
    dfs: list[pl.DataFrame] = []
    for s3_path in parquet_s3_paths:
        df = _download_single_parquet_file_as_dataframe(s3_path)
        dfs.append(df)

    combined_df = pl.concat(dfs)
    return combined_df

# TODO: awaiting https://cursor.com/agents/bc-5eae4bc0-3be5-4f91-804a-fe91da9610d2
def list_parquet_s3_keys(bucket: str, prefix: str) -> list[str]:
    ...

def upload_dataset_to_s3(dataset: Dataset):
    # TODO: awaiting https://cursor.com/agents/bc-5eae4bc0-3be5-4f91-804a-fe91da9610d2
    pass

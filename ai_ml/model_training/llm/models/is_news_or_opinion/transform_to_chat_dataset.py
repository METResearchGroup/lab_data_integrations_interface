"""Loads the raw records and transforms into a chat-style dataset and re-uploads to S3.

Uses shared tooling while defining its own `transform_dataset` function.
"""

from datasets import Dataset
import polars as pl

from ai_ml.model_training.llm.models.is_news_or_opinion.prompt import SYSTEM_PROMPT
from ai_ml.model_training.llm.shared.transform_to_chat_dataset import (
    download_parquet_training_set,
    list_parquet_s3_keys,
    upload_dataset_to_s3
)

S3_BUCKET = "met-ml-training"
S3_PREFIX = "mirrorview/create_feature_generation_training_sets_2026_09_04/is_news_or_opinion/"

def transform_dataset(df: pl.DataFrame) -> Dataset:
    records = [
        {
            "uri": row["uri"],
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": row["text"]},
                {"role": "assistant", "content": row["category"]},
            ],
        }
        for row in df.iter_rows(named=True)
    ]
    return Dataset.from_list(records)

if __name__ == "__main__":
    parquet_s3_paths: list[str] = list_parquet_s3_keys(bucket=S3_BUCKET, prefix=S3_PREFIX)
    df: pl.DataFrame = download_parquet_training_set(parquet_s3_paths=parquet_s3_paths)
    dataset: Dataset = transform_dataset(df)
    upload_dataset_to_s3(dataset)

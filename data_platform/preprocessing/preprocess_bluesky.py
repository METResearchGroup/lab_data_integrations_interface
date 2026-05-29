from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

import pandas as pd
from pydantic import TypeAdapter, ValidationError

from data_platform.models.sync import SyncBlueskyPostModel
from data_platform.preprocessing.validators.validators import (
    check_if_not_phone,
    check_if_post_has_no_urls,
    check_if_text_english,
    check_if_valid_post_length,
)
from lib.timestamp_utils import get_current_timestamp

PREPROCESSED_ROOT = Path(__file__).resolve().parents[1] / "data/bluesky/preprocessed"
TEXT_COLUMN = "text"

_SYNC_BLUESKY_POSTS_ADAPTER = TypeAdapter(list[SyncBlueskyPostModel])

TextValidator = Callable[[str], bool]

POST_TEXT_VALIDATORS: tuple[TextValidator, ...] = (
    check_if_not_phone,
    check_if_valid_post_length,
    check_if_post_has_no_urls,
    check_if_text_english,
)


def passes_all_validators(
    text: str,
    validators: Sequence[TextValidator] = POST_TEXT_VALIDATORS,
) -> bool:
    return all(validator(text) for validator in validators)


def filter_posts(
    posts: pd.DataFrame,
    validators: Sequence[TextValidator] = POST_TEXT_VALIDATORS,
) -> pd.DataFrame:
    """Return only posts whose text passes every validator in the pipeline."""
    if posts.empty:
        return posts.copy()

    mask = posts[TEXT_COLUMN].map(lambda value: passes_all_validators(str(value), validators))
    return posts.loc[mask].reset_index(drop=True)


def run_preprocessing_pipeline(
    posts: pd.DataFrame,
    validators: Sequence[TextValidator] = POST_TEXT_VALIDATORS,
) -> pd.DataFrame:
    return filter_posts(posts, validators)


def validate_load(posts: pd.DataFrame) -> pd.DataFrame:
    """Validate loaded posts against SyncBlueskyPostModel; raise on failure."""
    if posts.empty:
        return posts.copy()

    try:
        _SYNC_BLUESKY_POSTS_ADAPTER.validate_python(posts.to_dict(orient="records"))
    except ValidationError as exc:
        raise ValueError("Loaded posts failed SyncBlueskyPostModel validation") from exc

    return posts


def load_posts() -> pd.DataFrame:
    """Load raw posts for preprocessing. Stub until raw I/O is wired up."""
    return pd.DataFrame(columns=list(SyncBlueskyPostModel.model_fields.keys()))


def save_preprocessed_posts(posts: pd.DataFrame) -> Path:
    """Persist preprocessed posts. Stub until preprocessed I/O is wired up."""
    output_dir = PREPROCESSED_ROOT / get_current_timestamp()
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def preprocess_records() -> Path:
    posts = validate_load(load_posts())
    preprocessed = run_preprocessing_pipeline(posts)
    output_dir = save_preprocessed_posts(preprocessed)
    print(
        f"preprocess_records: kept {len(preprocessed)} of {len(posts)} posts -> {output_dir}"
    )
    return output_dir

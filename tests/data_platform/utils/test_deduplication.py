from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from data_platform.utils.deduplication import (
    DedupeConfig,
    DedupePolicy,
    DedupeSession,
    parse_policies,
)


def test_parse_policies_requires_current_run() -> None:
    with pytest.raises(ValueError, match="current_run"):
        parse_policies(["prior_runs_same_dataset"])


def test_parse_policies_rejects_both_prior_policies() -> None:
    with pytest.raises(ValueError, match="both prior_runs"):
        parse_policies(
            [
                "current_run",
                "prior_runs_same_dataset",
                "prior_runs_all_datasets",
            ]
        )


def test_parse_policies_rejects_empty_list() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        parse_policies([])


def test_session_warm_current_run_only() -> None:
    storage = MagicMock()
    storage.load_seen_ids.return_value = {"uri-a", "uri-b"}
    config = DedupeConfig(
        policies=[DedupePolicy.CURRENT_RUN],
        id_column="uri",
        filename="posts.csv",
    )
    session = DedupeSession(config)
    session.warm(storage, Path("/tmp/run"))

    assert session.seen_ids == {"uri-a", "uri-b"}
    storage.load_seen_ids.assert_called_once_with(Path("/tmp/run"), "uri", filename="posts.csv")
    storage.load_seen_ids_from_prior_runs.assert_not_called()
    storage.load_seen_ids_from_platform_raw_runs.assert_not_called()


def test_session_filter_rows_skips_seen() -> None:
    config = DedupeConfig(policies=[DedupePolicy.CURRENT_RUN], id_column="uri")
    session = DedupeSession(config)
    session.seen_ids = {"uri-a"}

    kept, skipped = session.filter_rows(
        [
            {"uri": "uri-a", "text": "dup"},
            {"uri": "uri-b", "text": "new"},
        ]
    )

    assert kept == [{"uri": "uri-b", "text": "new"}]
    assert skipped == 1


def test_note_appended_updates_seen_ids() -> None:
    config = DedupeConfig(policies=[DedupePolicy.CURRENT_RUN], id_column="uri")
    session = DedupeSession(config)
    session.seen_ids = {"uri-a"}

    session.note_appended([{"uri": "uri-b"}, {"uri": "uri-c"}])

    assert session.seen_ids == {"uri-a", "uri-b", "uri-c"}


def test_from_ingestion_params_parses_policy_key() -> None:
    config = DedupeConfig.from_ingestion_params(
        {"comments_dedupe_policy": ["current_run", "prior_runs_same_dataset"]},
        "comment_fullname",
        filename="comments.csv",
        policy_key="comments_dedupe_policy",
    )
    assert config.policies == [
        DedupePolicy.CURRENT_RUN,
        DedupePolicy.PRIOR_RUNS_SAME_DATASET,
    ]
    assert config.id_column == "comment_fullname"
    assert config.filename == "comments.csv"

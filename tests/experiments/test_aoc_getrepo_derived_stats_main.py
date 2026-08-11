"""Mocked end-to-end tests for main.run and write_outputs."""

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from experiments.aoc_getrepo_derived_stats_2026_08_11.discovery import (
    CohortMember,
    CohortResult,
)
from experiments.aoc_getrepo_derived_stats_2026_08_11.fetch_repos import RepoBundle
from experiments.aoc_getrepo_derived_stats_2026_08_11.main import run
from experiments.aoc_getrepo_derived_stats_2026_08_11.output import write_outputs
from experiments.aoc_getrepo_derived_stats_2026_08_11.records import PostRow
from experiments.aoc_getrepo_derived_stats_2026_08_11.schemas import empty_derived_stats_shell


def _member(did: str, handle: str, is_seed: bool = False) -> CohortMember:
    return CohortMember(
        did=did,
        handle=handle,
        followers_count=10,
        display_name=None,
        is_seed=is_seed,
    )


class TestWriteOutputs:
    """Tests for write_outputs()."""

    def test_writes_expected_files_and_null_csv_columns(self, tmp_path, monkeypatch):
        """Output folder contains required artifacts with None saved/unfollow."""
        monkeypatch.setattr(
            "experiments.aoc_getrepo_derived_stats_2026_08_11.output.OUTPUT_ROOT",
            tmp_path,
        )
        run_start = datetime(2026, 8, 11, 12, 0, 0, tzinfo=UTC)
        window_start = datetime(2026, 2, 10, 12, 0, 0, tzinfo=UTC)
        members = [
            _member("did:plc:aoc", "aoc.bsky.social", is_seed=True),
            _member("did:plc:u1", "u1.bsky.social"),
        ]
        bundles = [
            RepoBundle(
                did="did:plc:aoc",
                handle="aoc.bsky.social",
                posts=[
                    PostRow(
                        uri="at://did:plc:aoc/app.bsky.feed.post/1",
                        created_at="2026-07-01T00:00:00.000Z",
                        text="hi",
                        is_reply=False,
                        reply_parent_uri=None,
                        reply_root_uri=None,
                        langs="",
                        embed_type=None,
                        quoted_post_uri=None,
                        mentioned_dids="",
                        linked_uris="",
                    )
                ],
            ),
            RepoBundle(
                did="did:plc:u1",
                handle="u1.bsky.social",
                error="getRepo failed: boom",
            ),
        ]
        derived = [
            empty_derived_stats_shell(
                did=member.did,
                handle=member.handle,
                window_start=window_start.isoformat(),
                window_end=run_start.isoformat(),
            )
            for member in members
        ]

        output_dir = write_outputs(
            members, bundles, derived, run_start, window_start, run_start
        )

        assert (output_dir / "metadata.json").is_file()
        assert (output_dir / "derived_stats.json").is_file()
        assert (output_dir / "derived_stats.csv").is_file()
        assert (output_dir / "raw" / "posts.csv").is_file()

        metadata = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
        assert metadata["users_requested_followers"] == 50
        assert metadata["cohort_size_expected_max"] == 51
        assert len(metadata["errors"]) == 1

        frame = pd.read_csv(output_dir / "derived_stats.csv")
        assert pd.isna(frame.loc[0, "saved_posts"])
        assert pd.isna(frame.loc[0, "unfollow_actions"])
        assert frame.loc[0, "saved_posts"] != "[]"
        assert frame.loc[0, "unfollow_actions"] != "[]"


class TestRun:
    """Tests for run() orchestration."""

    def test_run_writes_outputs_with_mocked_network(self, tmp_path, monkeypatch):
        """run() wires discovery → fetch → derive → write without live APIs."""
        monkeypatch.setattr(
            "experiments.aoc_getrepo_derived_stats_2026_08_11.output.OUTPUT_ROOT",
            tmp_path,
        )
        members = (
            _member("did:plc:aoc", "aoc.bsky.social", is_seed=True),
            _member("did:plc:u1", "u1.bsky.social"),
            _member("did:plc:u2", "u2.bsky.social"),
        )
        cohort = CohortResult(members=members, target_did="did:plc:aoc")
        bundles = [
            RepoBundle(did="did:plc:aoc", handle="aoc.bsky.social"),
            RepoBundle(did="did:plc:u1", handle="u1.bsky.social", error="fail"),
            RepoBundle(did="did:plc:u2", handle="u2.bsky.social"),
        ]

        with (
            patch(
                "experiments.aoc_getrepo_derived_stats_2026_08_11.main.create_public_client",
                return_value=MagicMock(),
            ),
            patch(
                "experiments.aoc_getrepo_derived_stats_2026_08_11.main.create_relay_client",
                return_value=MagicMock(),
            ),
            patch(
                "experiments.aoc_getrepo_derived_stats_2026_08_11.main.discover_cohort",
                return_value=cohort,
            ),
            patch(
                "experiments.aoc_getrepo_derived_stats_2026_08_11.main.fetch_cohort_repos",
                return_value=bundles,
            ),
        ):
            run()

        output_dirs = list(tmp_path.iterdir())
        assert len(output_dirs) == 1
        output_dir = output_dirs[0]
        stats = json.loads((output_dir / "derived_stats.json").read_text(encoding="utf-8"))
        assert len(stats) == 3
        errored = next(row for row in stats if row["did"] == "did:plc:u1")
        assert errored["saved_posts"] is None
        assert errored["unfollow_actions"] is None
        metadata = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
        assert metadata["errors"]

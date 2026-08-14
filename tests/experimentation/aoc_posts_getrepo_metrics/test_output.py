"""Tests for metrics CSV and metadata writers."""

import csv
import json
from pathlib import Path

import pytest

from experimentation.aoc_posts_getrepo_metrics import output as output_module
from experimentation.aoc_posts_getrepo_metrics.constants import CSV_FIELDNAMES
from experimentation.aoc_posts_getrepo_metrics.metrics import derive_row
from experimentation.aoc_posts_getrepo_metrics.output import write_outputs


class TestWriteOutputs:
    """Tests for write_outputs()."""

    def test_write_outputs_creates_csv_and_metadata(self, tmp_path: Path, monkeypatch) -> None:
        """Creates posts_metrics.csv and metadata.json under the run folder."""
        monkeypatch.setattr(output_module, "OUTPUT_ROOT", tmp_path)
        row = derive_row(
            "at://did:plc:aoc/app.bsky.feed.post/1",
            {
                "$type": "app.bsky.feed.post",
                "text": "hello",
                "createdAt": "2026-01-01T00:00:00.000Z",
                "langs": ["en"],
            },
        )
        metadata = {
            "sync_timestamp": "2026_08_11-12:00:00",
            "target_handle": "aoc.bsky.social",
            "target_did": "did:plc:aoc",
            "min_posts": 50,
            "post_uri_count": 1,
            "rows_with_repo_record": 1,
            "rows_missing_repo_record": 0,
            "source_listing": "app.bsky.feed.getAuthorFeed",
            "source_repo": "com.atproto.sync.getRepo",
            "get_repo_calls": 1,
        }

        output_dir = write_outputs([row], metadata, "2026_08_11-12:00:00")

        csv_path = output_dir / "posts_metrics.csv"
        metadata_path = output_dir / "metadata.json"
        assert csv_path.is_file()
        assert metadata_path.is_file()
        with csv_path.open(encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            assert reader.fieldnames == CSV_FIELDNAMES
            rows = list(reader)
        assert len(rows) == 1
        assert json.loads(metadata_path.read_text(encoding="utf-8"))["get_repo_calls"] == 1

    def test_write_outputs_empty_none_cells(self, tmp_path: Path, monkeypatch) -> None:
        """Writes None engagement fields as empty CSV cells, not the string None."""
        monkeypatch.setattr(output_module, "OUTPUT_ROOT", tmp_path)
        row = derive_row("at://did:plc:aoc/app.bsky.feed.post/1", None)

        output_dir = write_outputs([row], {"get_repo_calls": 1}, "2026_08_11-12:00:01")

        with (output_dir / "posts_metrics.csv").open(encoding="utf-8") as handle:
            loaded = list(csv.DictReader(handle))[0]
        assert loaded["like_count"] == ""
        assert loaded["counts_read_at"] == ""
        assert "None" not in loaded["like_count"]

    def test_write_outputs_rejects_existing_run_directory(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Raises FileExistsError when the run folder already exists."""
        monkeypatch.setattr(output_module, "OUTPUT_ROOT", tmp_path)
        row = derive_row("at://did:plc:aoc/app.bsky.feed.post/1", None)
        metadata = {"get_repo_calls": 1}
        timestamp = "2026_08_11-12:00:02"

        write_outputs([row], metadata, timestamp)

        with pytest.raises(FileExistsError):
            write_outputs([row], metadata, timestamp)

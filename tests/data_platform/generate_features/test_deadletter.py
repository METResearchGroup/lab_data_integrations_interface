from __future__ import annotations

import json
from pathlib import Path

from data_platform.generate_features.deadletter import append_deadletter_batch, deadletter_path


def test_append_deadletter_batch_writes_jsonl(tmp_path: Path) -> None:
    features_dir = tmp_path / "features"
    append_deadletter_batch(
        features_dir,
        feature="is_political",
        uris=["at://a/post/1", "at://b/post/2"],
        error="RateLimitError: quota",
        attempts=4,
        batch_index=3,
    )
    path = deadletter_path(features_dir)
    assert path.exists()
    record = json.loads(path.read_text(encoding="utf-8").strip())
    assert record["feature"] == "is_political"
    assert record["uris"] == ["at://a/post/1", "at://b/post/2"]
    assert record["attempts"] == 4
    assert record["batch_index"] == 3

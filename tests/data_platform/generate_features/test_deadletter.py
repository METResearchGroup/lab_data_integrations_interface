from __future__ import annotations

import json

from data_platform.generate_features.deadletter import append_deadletter_batch, deadletter_path
from tests.data_platform.constants import URI_POST_A, URI_POST_B


def test_append_deadletter_batch_writes_jsonl(features_dir) -> None:
    append_deadletter_batch(
        features_dir,
        feature="is_political",
        uris=[URI_POST_A, URI_POST_B],
        error="RateLimitError: quota",
        attempts=4,
        batch_index=3,
    )
    path = deadletter_path(features_dir)
    assert path.exists()
    record = json.loads(path.read_text(encoding="utf-8").strip())
    assert record["feature"] == "is_political"
    assert record["uris"] == [URI_POST_A, URI_POST_B]
    assert record["attempts"] == 4
    assert record["batch_index"] == 3

from types import SimpleNamespace

import pandas as pd

from experiments.parquet_posts_2022_03_10.main import post_url, unique_uris, write_post_links


def test_unique_uris_keeps_first_occurrence_order(tmp_path):
    df = pd.DataFrame(
        {
            "uri": [
                "at://did:plc:a/app.bsky.feed.post/1",
                "at://did:plc:b/app.bsky.feed.post/2",
                "at://did:plc:a/app.bsky.feed.post/1",
            ]
        }
    )
    assert unique_uris(df) == [
        "at://did:plc:a/app.bsky.feed.post/1",
        "at://did:plc:b/app.bsky.feed.post/2",
    ]


def test_post_url_uses_handle_and_rkey():
    post = SimpleNamespace(
        uri="at://did:plc:lyblenqvfetjzcdy76w6ohyy/app.bsky.feed.post/3itvvfle3w2wa",
        author=SimpleNamespace(handle="nieuws.nos.nl"),
    )
    assert post_url(post) == "https://bsky.app/profile/nieuws.nos.nl/post/3itvvfle3w2wa"


def test_write_post_links_marks_missing_uris(tmp_path, monkeypatch):
    from experiments.parquet_posts_2022_03_10 import main as module

    out = tmp_path / "post_links.jsonl"
    monkeypatch.setattr(module, "JSONL_PATH", out)
    found = SimpleNamespace(
        uri="at://did:plc:a/app.bsky.feed.post/1",
        cid="bafytest",
        author=SimpleNamespace(handle="alice.test", did="did:plc:a"),
        record=SimpleNamespace(model_dump=lambda mode="json": {"text": "hello"}),
    )
    write_post_links(
        [
            "at://did:plc:a/app.bsky.feed.post/1",
            "at://did:plc:b/app.bsky.feed.post/missing",
        ],
        {"at://did:plc:a/app.bsky.feed.post/1": found},
    )
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    import json

    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert first["found"] is True
    assert first["url"] == "https://bsky.app/profile/alice.test/post/1"
    assert first["record"] == {"text": "hello"}
    assert second == {
        "uri": "at://did:plc:b/app.bsky.feed.post/missing",
        "found": False,
        "url": None,
        "cid": None,
        "author_handle": None,
        "author_did": None,
        "record": None,
    }

from datetime import UTC, datetime

from experiments.jetstream_old_vs_new_posts_2026_08_18.tid import (
    decode_tid_microseconds,
    rkey_from_uri,
    tid_datetime,
)


def test_known_rkey_tid_matches_created_at():
    # rkey from the 2022-01-11 example file; timestamp equals created_at.
    assert decode_tid_microseconds("3ipeokhysc2an") == 1_641_936_484_000_000
    assert tid_datetime("3ipeokhysc2an") == datetime(2022, 1, 11, 21, 28, 4, tzinfo=UTC)


def test_known_rev_tid_is_ingest_era():
    # rev from the same row; this is the commit clock, not the article clock.
    decoded = tid_datetime("3mstxz7232i2d")
    assert decoded is not None
    assert decoded.date() == datetime(2026, 8, 12, tzinfo=UTC).date()


def test_rejects_non_tids():
    assert decode_tid_microseconds("short") is None
    assert decode_tid_microseconds("3ipeokhysc2a!") is None
    assert tid_datetime("not-a-tid") is None


def test_rkey_from_uri():
    uri = "at://did:plc:abc/app.bsky.feed.post/3ipeokhysc2an"
    assert rkey_from_uri(uri) == "3ipeokhysc2an"

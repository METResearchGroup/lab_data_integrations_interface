from __future__ import annotations

VALID_DATASET_ID = "bluesky_00000000-0000-4000-8000-000000000001"
FEATURES_DATASET_ID = "bluesky_f47ac10b-58cc-4372-a567-0e02b2c3d479"

URI_POST_A = "at://a/post/1"
URI_POST_B = "at://b/post/2"

PREPROCESSED_RUN = "preprocessed/2026_01_01-00:00:00"
PREPROCESSED_RUN_DIR = "2026_01_01-00:00:00"
LABEL_TIMESTAMP = "2026_01_01-00:00:00"

SAMPLE_INGESTION_ROW = {
    "uri": "at://did:plc:example/app.bsky.feed.post/abc",
    "url": "https://bsky.app/profile/handle/post/abc",
    "author_handle": "handle",
    "text": "hello",
    "created_at": "2026-05-30T00:00:00.000Z",
    "like_count": 1,
    "repost_count": 0,
    "reply_count": 0,
    "quote_count": 0,
}

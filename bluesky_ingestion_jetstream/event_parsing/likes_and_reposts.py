"""Parse `app.bsky.feed.like` and `app.bsky.feed.repost` commits."""

from bluesky_ingestion_jetstream.event_parsing.shared import as_dict, as_str


def parse_like_or_repost(record: dict) -> dict:
    """Extract the like/repost columns."""

    # `subject` is a strongref object here, unlike follows.
    subject = as_dict(record.get("subject"))

    return {
        "subject_uri": as_str(subject.get("uri")),
        "subject_cid": as_str(subject.get("cid")),
    }

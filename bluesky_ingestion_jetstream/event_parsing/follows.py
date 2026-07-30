"""Parse `app.bsky.graph.follow` commits."""

from bluesky_ingestion_jetstream.event_parsing.shared import as_str


def parse_follow(record: dict) -> dict:
    """Extract the follow columns."""

    # `subject` is a bare DID string here, not a strongref object like likes and
    # reposts use. Reading it as `subject["uri"]` would null every follow.
    return {"subject_did": as_str(record.get("subject"))}

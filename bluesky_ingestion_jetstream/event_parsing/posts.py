"""Parse `app.bsky.feed.post` commits."""

from bluesky_ingestion_jetstream.event_parsing.shared import as_dict, as_str, as_str_list


def parse_post(record: dict) -> dict:
    """Extract the post columns."""

    reply = as_dict(record.get("reply"))

    return {
        "text": as_str(record.get("text")),
        "langs": as_str_list(record.get("langs")),
        # Null reply URIs mean a top-level post.
        "reply_root_uri": as_str(as_dict(reply.get("root")).get("uri")),
        "reply_parent_uri": as_str(as_dict(reply.get("parent")).get("uri")),
        # The discriminator only, not the embed payload.
        "embed_type": as_str(as_dict(record.get("embed")).get("$type")),
    }

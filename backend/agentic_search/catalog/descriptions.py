"""Hand-written column and table meaning. Names and types come from Iceberg; this does not."""

from bluesky_ingestion_jetstream.constants import FOLLOWS, LIKES, POSTS, REPOSTS

TABLE_DESCRIPTIONS: dict[str, str] = {
    POSTS: "Bluesky posts, one row per post seen on the firehose.",
    LIKES: "Bluesky likes, one row per like of a post.",
    REPOSTS: "Bluesky reposts, one row per repost of a post.",
    FOLLOWS: "Bluesky follows, one row per follow of an account.",
}

_COMMON_COLUMNS: dict[str, str] = {
    "uri": "AT Protocol URI of the record.",
    "did": "DID of the account that created the record.",
    "cid": "Content hash of the record.",
    "rev": "Repo revision the record was written at.",
    "created_at": "Author's client clock. Tables are partitioned by day of this column.",
    "ingested_at": "When we wrote the record.",
    "run_id": "Ingester process that wrote the row.",
}

_RECORD_TYPE_COLUMNS: dict[str, dict[str, str]] = {
    POSTS: {
        "text": "Post body.",
        "langs": "Languages the author tagged the post with.",
        "reply_root_uri": "URI of the thread root, null unless the post is a reply.",
        "reply_parent_uri": "URI of the post replied to, null unless the post is a reply.",
        "embed_type": "Kind of attached media, null when the post has none.",
    },
    LIKES: {
        "subject_uri": "URI of the liked post.",
        "subject_cid": "Content hash of the liked post.",
    },
    REPOSTS: {
        "subject_uri": "URI of the reposted post.",
        "subject_cid": "Content hash of the reposted post.",
    },
    FOLLOWS: {"subject_did": "DID of the account being followed."},
}


def describe_column(record_type: str, column: str) -> str | None:
    """What a column means, or None if we have not written it down."""

    return _RECORD_TYPE_COLUMNS.get(record_type, {}).get(column) or _COMMON_COLUMNS.get(column)

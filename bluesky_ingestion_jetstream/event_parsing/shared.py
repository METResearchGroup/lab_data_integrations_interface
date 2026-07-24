"""Fields common to all commit types."""

from collections.abc import Iterable
from datetime import UTC, datetime


def as_dict(value: object) -> dict:
    """Return `value` if it is a dict, else an empty dict.

    Jetstream carries client-generated junk, so a nested field can arrive as the
    wrong type. Routing nested reads through this yields null columns instead of
    raising.
    """

    return value if isinstance(value, dict) else {}


def as_str(value: object) -> str | None:
    """Return `value` if it is a string, else None."""

    return value if isinstance(value, str) else None


def as_str_list(value: object) -> list[str] | None:
    """Return the string members of `value` if it is a list, else None."""

    if not isinstance(value, list):
        return None
    return [item for item in value if isinstance(item, str)]


def parse_created_at(value: object) -> datetime | None:
    """Parse a client-supplied ISO-8601 timestamp into UTC."""

    if not isinstance(value, str):
        return None

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_shared(event: dict) -> dict:
    """Extract the columns every commit type has."""

    commit = as_dict(event.get("commit"))
    record = as_dict(commit.get("record"))

    did = as_str(event.get("did"))
    collection = as_str(commit.get("collection"))
    rkey = as_str(commit.get("rkey"))

    return {
        # Not on the wire: Jetstream sends the parts, so the AT-URI is rebuilt.
        "uri": f"at://{did}/{collection}/{rkey}" if did and collection and rkey else None,
        "did": did,
        "cid": as_str(commit.get("cid")),
        "created_at": parse_created_at(record.get("createdAt")),
    }


def validate_non_null_fields(row: dict, required_keys: Iterable[str]) -> bool:
    """Whether every required key is present and non-null. False means drop the row."""

    return all(row.get(key) is not None for key in required_keys)

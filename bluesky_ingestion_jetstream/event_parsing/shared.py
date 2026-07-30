"""Fields common to all commit types."""

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


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


def parse_ingested_at(value: object) -> datetime | None:
    """Turn the envelope's `time_us` into a UTC timestamp.

    Added to the epoch as an integer `timedelta` rather than divided into a float
    and handed to `fromtimestamp`, so the arithmetic is exact by construction. The
    float route happens to round-trip at today's magnitudes, but only because a
    microsecond epoch still fits inside float64's exact-integer range.

    Unlike `created_at` this is the broker's clock, not the client's, so it is the
    trustworthy end of an `ingested_at - created_at` lag calculation. It is also
    stable under replay: a cursor rewind redelivers the same `time_us`, where a
    locally-stamped clock would give the same event a new value each time.
    """

    # bools are ints, and a `True` timestamp is junk rather than 1 microsecond.
    if not isinstance(value, int) or isinstance(value, bool):
        return None

    try:
        return EPOCH + timedelta(microseconds=value)
    except OverflowError:
        return None


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
        "rev": as_str(commit.get("rev")),
        "created_at": parse_created_at(record.get("createdAt")),
        "ingested_at": parse_ingested_at(event.get("time_us")),
    }


def validate_non_null_fields(row: dict, required_keys: Iterable[str]) -> bool:
    """Whether every required key is present and non-null. False means drop the row."""

    return all(row.get(key) is not None for key in required_keys)

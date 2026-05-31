from datetime import UTC, datetime

CREATED_AT_FORMAT: str = "%Y_%m_%d-%H:%M:%S"


def get_current_timestamp() -> str:
    """Get the current timestamp in the contract format."""

    return datetime.now(UTC).strftime(CREATED_AT_FORMAT)


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string for JSON metadata fields."""

    return datetime.now(UTC).isoformat()

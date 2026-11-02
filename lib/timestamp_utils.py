from datetime import UTC, date, datetime

CREATED_AT_FORMAT: str = "%Y_%m_%d-%H:%M:%S"


def get_current_datetime() -> datetime:
    return datetime.now(UTC)


def get_current_date() -> date:
    """The current calendar date in UTC."""

    return get_current_datetime().date()


def get_current_timestamp() -> str:
    """Get the current timestamp in the contract format."""

    return get_current_datetime().strftime(CREATED_AT_FORMAT)

"""Fields common to all commit types."""

from collections.abc import Iterable


def parse_shared(event: dict) -> dict:
    """Extract the columns every commit type has."""
    print(event)
    raise NotImplementedError


def validate_non_null_fields(row: dict, required_keys: Iterable[str]) -> bool:
    """Whether every required key is present and non-null. False means drop the row."""
    print(row)
    print(required_keys)
    raise NotImplementedError

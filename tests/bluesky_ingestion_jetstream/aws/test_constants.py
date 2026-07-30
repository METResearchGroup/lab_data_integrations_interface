"""Tests for the Glue/Iceberg configuration.

Deliberately short. Most of what lives in `aws/constants.py` is a literal, and a
test that restates a literal only fails when the literal is changed on purpose --
it reports edits, not defects. What is worth asserting is the handful of facts
that span two modules, or that AWS validates too late to be cheap.
"""

from bluesky_ingestion_jetstream.aws.constants import (
    PARTITION_SOURCE_COLUMN,
    TABLE_PROPERTIES,
)
from bluesky_ingestion_jetstream.schemas.arrow_schemas import RECORD_TYPE_TO_SCHEMA


def test_partition_source_column_exists_in_every_schema():
    """Renaming the column in the schemas has to fail here, not at bootstrap.

    `bootstrap.create_table` commits the table to Glue *before* `add_field`
    resolves this column, so a mismatch leaves a half-built table behind for
    someone to clean up by hand.
    """

    for schema in RECORD_TYPE_TO_SCHEMA.values():
        assert PARTITION_SOURCE_COLUMN in schema.names


def test_table_properties_are_strings():
    """Iceberg stores properties as strings, and rejects anything else at commit.

    Cheap to get wrong (`256 * 1024 * 1024` without the `str()`) and otherwise
    only caught against live AWS.
    """

    assert all(isinstance(value, str) for value in TABLE_PROPERTIES.values())

"""Connect to the Glue catalog and load the four Iceberg tables.

Runs on every process start, unlike `bootstrap.py`. Nothing here creates or
alters a table: an ingester that can issue DDL is one typo in a database name
away from quietly writing a full day of data into a second, empty set of tables
that looks fine until someone queries the real ones. Missing tables raise.
"""

from pyiceberg.catalog.glue import GlueCatalog
from pyiceberg.exceptions import NoSuchTableError
from pyiceberg.table import Table

from bluesky_ingestion_jetstream.aws.constants import (
    AWS_REGION,
    GLUE_DATABASE,
    S3_BUCKET,
    S3_PREFIX,
)
from bluesky_ingestion_jetstream.constants import RECORD_TYPES


class MissingTablesError(RuntimeError):
    """Raised when the catalog is missing tables `bootstrap.py` should have created."""


def build_catalog() -> GlueCatalog:
    """Construct the Glue-backed catalog.

    Left on PyIceberg's default PyArrowFileIO. The Iceberg experiment pinned
    FsspecFileIO so its S3 meter could see every request through aiobotocore;
    production has nothing to meter and PyArrow's client is faster.
    """

    return GlueCatalog(
        name="bluesky",
        **{
            "warehouse": f"s3://{S3_BUCKET}/{S3_PREFIX}",
            "glue.region": AWS_REGION,
            "s3.region": AWS_REGION,
        },
    )


def load_tables(catalog: GlueCatalog) -> dict[str, Table]:
    """Load every record type's table, or raise naming all the ones missing.

    Called once at startup rather than per flush, because each load is a Glue
    `GetTable` call. Every missing table is collected before raising, so a fresh
    environment reports all four in one go instead of one per re-run.
    """

    tables: dict[str, Table] = {}
    missing: list[str] = []

    for record_type in RECORD_TYPES:
        try:
            tables[record_type] = catalog.load_table((GLUE_DATABASE, record_type))
        except NoSuchTableError:
            missing.append(record_type)

    if missing:
        raise MissingTablesError(
            f"Glue database {GLUE_DATABASE!r} is missing table(s): {', '.join(missing)}. "
            "Run `python -m bluesky_ingestion_jetstream.aws.bootstrap` to create them."
        )

    return tables

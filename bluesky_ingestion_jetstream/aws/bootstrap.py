"""One-shot creation of the four Iceberg tables. Run by hand, not by the ingester.

    python -m bluesky_ingestion_jetstream.aws.bootstrap

Idempotent: tables that already exist are reported and left alone, so a partial
failure can be resolved by re-running. Dropping a table is not offered here --
it discards data, and doing it by hand is the point.

The Glue database itself is Terraform's
(`terraform/bluesky_ingestion_jetstream/main.tf`); the
tables are not, because Iceberg rewrites a table's schema, partition spec, and
snapshot pointer on every commit, which an `aws_glue_catalog_table` resource
would read as drift and revert on the next apply.
"""

from pyiceberg.catalog.glue import GlueCatalog
from pyiceberg.exceptions import NoSuchNamespaceError, TableAlreadyExistsError
from pyiceberg.table import Table
from pyiceberg.transforms import DayTransform

from bluesky_ingestion_jetstream.aws.catalog import build_catalog
from bluesky_ingestion_jetstream.aws.constants import (
    GLUE_DATABASE,
    PARTITION_FIELD_NAME,
    PARTITION_SOURCE_COLUMN,
    TABLE_LOCATIONS,
    TABLE_PROPERTIES,
)
from bluesky_ingestion_jetstream.schemas.arrow_schemas import RECORD_TYPE_TO_SCHEMA


def require_namespace(catalog: GlueCatalog) -> None:
    """Fail if Terraform has not created the Glue database yet."""

    try:
        catalog.list_tables(GLUE_DATABASE)
    except NoSuchNamespaceError as error:
        raise RuntimeError(
            f"Glue database {GLUE_DATABASE!r} does not exist. It is managed by "
            "Terraform -- run `terraform apply` in "
            "terraform/bluesky_ingestion_jetstream first."
        ) from error


def create_table(catalog: GlueCatalog, record_type: str) -> Table:
    """Create one partitioned table from its Arrow schema.

    The Arrow schema is passed through untouched so PyIceberg assigns the field
    IDs itself. Hand-written IDs are renumbered on create, and because Iceberg
    resolves columns by ID rather than name, any mismatch reads back as NULL for
    every affected column rather than failing. Not writing IDs at all removes
    that failure mode instead of guarding against it.
    """

    table = catalog.create_table(
        identifier=(GLUE_DATABASE, record_type),
        schema=RECORD_TYPE_TO_SCHEMA[record_type],
        location=TABLE_LOCATIONS[record_type],
        properties=TABLE_PROPERTIES,
    )

    # Partition after creation rather than passing a `PartitionSpec`, because
    # `add_field` takes the column name and resolves the source ID itself.
    table.update_spec().add_field(
        PARTITION_SOURCE_COLUMN, DayTransform(), PARTITION_FIELD_NAME
    ).commit()

    return table


def bootstrap(catalog: GlueCatalog | None = None) -> dict[str, Table]:
    """Create every missing table. Returns record type -> table for all four."""

    catalog = catalog or build_catalog()
    require_namespace(catalog)

    tables: dict[str, Table] = {}
    for record_type in RECORD_TYPE_TO_SCHEMA:
        try:
            tables[record_type] = create_table(catalog, record_type)
            print(f"created {GLUE_DATABASE}.{record_type} -> {TABLE_LOCATIONS[record_type]}")
        except TableAlreadyExistsError:
            tables[record_type] = catalog.load_table((GLUE_DATABASE, record_type))
            print(f"exists  {GLUE_DATABASE}.{record_type}")

    return tables


def main() -> None:
    """CLI entry point."""

    for record_type, table in bootstrap().items():
        print(f"{record_type}: {table.spec()}")


if __name__ == "__main__":
    main()

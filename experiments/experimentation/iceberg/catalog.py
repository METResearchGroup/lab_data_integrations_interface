"""Glue catalog wiring for the experiment.

Two things here are load-bearing:

1. ``py-io-impl`` is pinned to ``FsspecFileIO``. PyIceberg defaults to
   ``PyArrowFileIO``, whose S3 client lives in C++ and is invisible to the
   meter. Fsspec routes through aiobotocore, so every request is countable.
2. Tables are named ``<record_type>_<run_id>`` inside a single dedicated Glue
   database, so repeat runs never collide and cleanup is one prefix delete.
"""

from __future__ import annotations

from typing import Any

from pyiceberg.catalog import Catalog
from pyiceberg.catalog.glue import GlueCatalog
from pyiceberg.exceptions import NamespaceAlreadyExistsError, NoSuchTableError

from experimentation.iceberg import constants, schemas


def warehouse_uri(run_id: str) -> str:
    return f"s3://{constants.S3_BUCKET}/{constants.S3_EXPERIMENT_PREFIX}/{run_id}/warehouse"


def raw_uri(run_id: str) -> str:
    return f"s3://{constants.S3_BUCKET}/{constants.S3_EXPERIMENT_PREFIX}/{run_id}/raw"


def table_name(record_type: str, run_id: str) -> str:
    return f"{record_type}_{run_id}"


def build_catalog(run_id: str) -> Catalog:
    """Construct the Glue-backed catalog for this run."""
    return GlueCatalog(
        name="iceberg_experiment",
        **{
            "warehouse": warehouse_uri(run_id),
            "glue.region": constants.AWS_REGION,
            "s3.region": constants.AWS_REGION,
            # Required for the meter to see anything -- see module docstring.
            "py-io-impl": "pyiceberg.io.fsspec.FsspecFileIO",
        },
    )


def ensure_namespace(catalog: Catalog) -> None:
    try:
        catalog.create_namespace(constants.GLUE_DATABASE)
    except NamespaceAlreadyExistsError:
        pass


def create_tables(catalog: Catalog, run_id: str) -> dict[str, Any]:
    """Create one partitioned table per record type. Returns record_type -> Table."""
    ensure_namespace(catalog)
    tables: dict[str, Any] = {}

    for record_type in constants.RECORD_TYPES:
        identifier = (constants.GLUE_DATABASE, table_name(record_type, run_id))
        tables[record_type] = catalog.create_table(
            identifier=identifier,
            schema=schemas.SCHEMAS[record_type],
            partition_spec=schemas.PARTITION_SPEC,
            location=f"{warehouse_uri(run_id)}/{record_type}",
            properties={
                "format-version": "2",
                "write.parquet.compression-codec": "zstd",
                # Leave stale metadata.json files in place so the expiry phase
                # has real work to measure.
                "write.metadata.delete-after-commit.enabled": "false",
            },
        )
    return tables


def load_tables(catalog: Catalog, run_id: str) -> dict[str, Any]:
    """Load existing tables for a run, skipping any that were never created."""
    tables: dict[str, Any] = {}
    for record_type in constants.RECORD_TYPES:
        try:
            tables[record_type] = catalog.load_table(
                (constants.GLUE_DATABASE, table_name(record_type, run_id))
            )
        except NoSuchTableError:
            continue
    return tables


def drop_tables(catalog: Catalog, run_id: str) -> list[str]:
    """Drop this run's Glue tables. Does not remove the S3 objects behind them."""
    dropped = []
    for record_type in constants.RECORD_TYPES:
        name = table_name(record_type, run_id)
        try:
            catalog.drop_table((constants.GLUE_DATABASE, name))
            dropped.append(name)
        except NoSuchTableError:
            continue
    return dropped

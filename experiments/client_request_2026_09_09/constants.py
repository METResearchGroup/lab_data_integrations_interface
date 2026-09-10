"""Candidate table, query windows, and S3 layout for the 2026-09-09 export."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from bluesky_ingestion_jetstream.constants import DATA_START_DATE

S3_BUCKET = "lab-data-integrations-interface"
S3_PREFIX = "experiments/client_request_2026_09_09"
GLUE_DATABASE = "bluesky_raw"
GLUE_TABLE = "posts"
WORKGROUP = "bluesky_raw_maintenance"
SMOKE_LIMIT = 100

UNLOAD_DIR_NAME = "unload"
POSTS_PARQUET_FILENAME = "posts.parquet"
METADATA_FILENAME = "metadata.json"
PARQUET_FILE_COMPRESSION = "zstd"
UNLOAD_SQL_FORMAT = "PARQUET"
UNLOAD_SQL_COMPRESSION = "ZSTD"
JSON_INDENT = 2
UTF8_ENCODING = "utf-8"
S3_URI_SCHEME = "s3://"
MIDNIGHT_CLOCK = "00:00:00"
EXCLUSIVE_END_OFFSET_DAYS = 1
SINGLE_CANDIDATE_EXPORT_COUNT = 1

MATCH_RULE = "case_insensitive_substring_on_text"
IS_CRITICISM_FILTER = False

METADATA_NOTES = (
    "Rows are name matches on post text, not posts labeled as criticisms.",
    (
        "Query windows start on max(primary_date, "
        f"{DATA_START_DATE.isoformat()}). Jetstream Iceberg coverage of posts begins "
        f"{DATA_START_DATE.isoformat()}."
    ),
)

CANDIDATE_ID_EL_SAYED = "el_sayed"
CANDIDATE_ID_TALARICO = "talarico"
CANDIDATE_ID_BECERRA = "becerra"
CANDIDATE_ID_COOPER = "cooper"
CANDIDATE_ID_OSSOFF = "ossoff"

DISPLAY_NAME_EL_SAYED = "Abdul El-Sayed"
DISPLAY_NAME_TALARICO = "James Talarico"
DISPLAY_NAME_BECERRA = "Xavier Becerra"
DISPLAY_NAME_COOPER = "Roy Cooper"
DISPLAY_NAME_OSSOFF = "Jon Ossoff"

PRIMARY_DATE_EL_SAYED = date(2026, 8, 4)
PRIMARY_DATE_TALARICO = date(2026, 3, 3)
PRIMARY_DATE_BECERRA = date(2026, 6, 2)
PRIMARY_DATE_COOPER = date(2026, 3, 3)
PRIMARY_DATE_OSSOFF = date(2026, 5, 19)

EL_SAYED_NAME_STRINGS = (
    "abdul el-sayed",
    "el-sayed",
    "el sayed",
    "elsayed",
)
TALARICO_NAME_STRINGS = ("james talarico", "talarico")
BECERRA_NAME_STRINGS = ("xavier becerra", "xavier beccera", "becerra")
COOPER_NAME_STRINGS = ("roy cooper",)
OSSOFF_NAME_STRINGS = ("jon ossoff", "jonathan ossoff", "ossoff")


@dataclass(frozen=True)
class Candidate:
    """One person in the Iceberg name-match export."""

    candidate_id: str
    display_name: str
    primary_date: date
    name_strings: tuple[str, ...]


CANDIDATES: tuple[Candidate, ...] = (
    Candidate(
        candidate_id=CANDIDATE_ID_EL_SAYED,
        display_name=DISPLAY_NAME_EL_SAYED,
        primary_date=PRIMARY_DATE_EL_SAYED,
        name_strings=EL_SAYED_NAME_STRINGS,
    ),
    Candidate(
        candidate_id=CANDIDATE_ID_TALARICO,
        display_name=DISPLAY_NAME_TALARICO,
        primary_date=PRIMARY_DATE_TALARICO,
        name_strings=TALARICO_NAME_STRINGS,
    ),
    Candidate(
        candidate_id=CANDIDATE_ID_BECERRA,
        display_name=DISPLAY_NAME_BECERRA,
        primary_date=PRIMARY_DATE_BECERRA,
        name_strings=BECERRA_NAME_STRINGS,
    ),
    Candidate(
        candidate_id=CANDIDATE_ID_COOPER,
        display_name=DISPLAY_NAME_COOPER,
        primary_date=PRIMARY_DATE_COOPER,
        name_strings=COOPER_NAME_STRINGS,
    ),
    Candidate(
        candidate_id=CANDIDATE_ID_OSSOFF,
        display_name=DISPLAY_NAME_OSSOFF,
        primary_date=PRIMARY_DATE_OSSOFF,
        name_strings=OSSOFF_NAME_STRINGS,
    ),
)

CANDIDATES_BY_ID: dict[str, Candidate] = {
    candidate.candidate_id: candidate for candidate in CANDIDATES
}


def query_start_date(primary_date: date) -> date:
    """Return the later of the primary date and Jetstream coverage start.

    Parameters
    ----------
    primary_date
        Candidate primary date.

    Returns
    -------
    date
        Inclusive query start used in Athena SQL.
    """

    return max(primary_date, DATA_START_DATE)


def query_end_date(run_date: date) -> date:
    """Return the inclusive UTC calendar end date of a run.

    Parameters
    ----------
    run_date
        UTC date of the export run.

    Returns
    -------
    date
        Inclusive end. SQL treats the next midnight as exclusive.
    """

    return run_date


def s3_object_uri(object_key: str) -> str:
    """Build an ``s3://`` URI for a key in the experiment bucket."""

    return f"{S3_URI_SCHEME}{S3_BUCKET}/{object_key}"


def unload_object_prefix(run_timestamp: str, candidate_id: str) -> str:
    """Return the UNLOAD key prefix, including the trailing slash."""

    return f"{S3_PREFIX}/{run_timestamp}/{UNLOAD_DIR_NAME}/{candidate_id}/"


def candidate_parquet_object_key(run_timestamp: str, candidate_id: str) -> str:
    """Return the merged per-candidate Parquet object key."""

    return f"{S3_PREFIX}/{run_timestamp}/{candidate_id}.parquet"


def posts_parquet_object_key(run_timestamp: str) -> str:
    """Return the combined posts Parquet object key."""

    return f"{S3_PREFIX}/{run_timestamp}/{POSTS_PARQUET_FILENAME}"


def metadata_object_key(run_timestamp: str) -> str:
    """Return the metadata JSON object key."""

    return f"{S3_PREFIX}/{run_timestamp}/{METADATA_FILENAME}"

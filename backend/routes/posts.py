from fastapi import APIRouter, HTTPException

from data_platform.aws.athena import Athena
from data_platform.aws.constants import OLAP_WORKGROUP
from data_platform.aws.s3 import S3

router = APIRouter()

PREVIEW_LIMIT = 20


def _escape(value: str) -> str:
    """Escape single quotes in SQL string literals."""
    return value.replace("'", "''")


def _escape_like(value: str) -> str:
    """Escape SQL string delimiters and LIKE metacharacters (using ! as escape char)."""
    value = value.replace("'", "''")
    value = value.replace("!", "!!")
    value = value.replace("%", "!%")
    value = value.replace("_", "!_")
    return value


def _partition_filter(dataset_id: str) -> str:
    return f"platform = 'bluesky' AND dataset_id = '{_escape(dataset_id)}'"


def _run_and_build_download(sql: str) -> tuple[list[dict[str, str]], str]:
    athena = Athena()
    execution_id = athena.run_query(sql, workgroup=OLAP_WORKGROUP)
    rows = athena.fetch_rows(execution_id)
    download_url = S3().generate_presigned_url(athena.get_output_location(execution_id))
    return rows, download_url


@router.get("/posts/recent", status_code=200)
def get_recent_posts(dataset_id: str):
    """Return the 20 most recent posts ordered by created_at descending."""
    sql = f"""
        SELECT uri, url, author_handle, text, created_at,
               like_count, repost_count, reply_count, quote_count
        FROM bluesky_raw
        WHERE {_partition_filter(dataset_id)}
        ORDER BY created_at DESC
        LIMIT {PREVIEW_LIMIT}
    """
    rows, download_url = _run_and_build_download(sql)
    return {"rows": rows, "download_url": download_url}


@router.get("/posts/top-authors", status_code=200)
def get_top_authors(dataset_id: str):
    """Return the top 20 authors by post count."""
    sql = f"""
        SELECT author_handle, COUNT(*) AS post_count
        FROM bluesky_raw
        WHERE {_partition_filter(dataset_id)}
        GROUP BY author_handle
        ORDER BY post_count DESC
        LIMIT {PREVIEW_LIMIT}
    """
    rows, download_url = _run_and_build_download(sql)
    return {"rows": rows, "download_url": download_url}


@router.get("/posts/keyword-count", status_code=200)
def get_keyword_count(dataset_id: str, keyword: str):
    """Return how many posts contain keyword in their text."""
    if not keyword.strip():
        raise HTTPException(status_code=422, detail="keyword must not be blank")
    sql = f"""
        SELECT COUNT(*) AS count
        FROM bluesky_raw
        WHERE {_partition_filter(dataset_id)}
        AND LOWER(text) LIKE '%{_escape_like(keyword.lower())}%' ESCAPE '!'
    """
    athena = Athena()
    execution_id = athena.run_query(sql, workgroup=OLAP_WORKGROUP)
    rows = athena.fetch_rows(execution_id)
    count = int(rows[0]["count"]) if rows else 0
    return {"keyword": keyword, "count": count}

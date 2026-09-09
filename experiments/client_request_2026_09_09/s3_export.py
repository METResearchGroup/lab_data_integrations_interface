"""Download Athena UNLOAD Parquet parts and merge them locally.

Copied from the Perspective labeling export helpers, without S3 deletes.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from experiments.client_request_2026_09_09.constants import PARQUET_FILE_COMPRESSION


def download_s3_prefix(s3_client, bucket: str, prefix: str, dest: Path) -> list[Path]:
    """Download every non-folder object under ``prefix`` into ``dest``.

    Parameters
    ----------
    s3_client
        Boto3 S3 client, or a test double with ``get_paginator`` and
        ``download_file``.
    bucket
        Bucket that holds the UNLOAD parts.
    prefix
        Key prefix, including the trailing slash.
    dest
        Local directory that receives the files.

    Returns
    -------
    list[Path]
        Local paths of downloaded objects, in listing order.
    """

    dest.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):
                continue
            filename = Path(key).name
            local_path = dest / filename
            s3_client.download_file(bucket, key, str(local_path))
            downloaded.append(local_path)
    return downloaded


def merge_parquet_files(parquet_paths: list[Path], output_path: Path) -> int:
    """Concatenate Parquet parts into one zstd file.

    Parameters
    ----------
    parquet_paths
        Local part files. An empty list is a caller error; write an empty
        combined table instead.
    output_path
        Merged Parquet destination.

    Returns
    -------
    int
        Row count of the merged table.
    """

    tables = [pq.read_table(path) for path in sorted(parquet_paths)]
    combined = pa.concat_tables(tables)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(combined, output_path, compression=PARQUET_FILE_COMPRESSION)
    return combined.num_rows

"""S3 + SQLite deduplication backend.

Workflow per pipeline run:
  1. Download SQLite file from S3
  2. Query in-memory for already-seen URIs
  3. Write new URIs to local SQLite
  4. Upload file back to S3

Run from repo root:
    PYTHONPATH=. uv run python experiments/dedup_comparison_2026_06_12/sqlite_backend.py
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import boto3  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

BUCKET = "lab-data-integrations-dedup-experiment-use2"
S3_KEY = "dedup-experiment/seen.db"

_PRAGMAS = [
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA cache_size=-64000",
    "PRAGMA mmap_size=268435456",
    "PRAGMA temp_store=MEMORY",
]


class SQLiteBackend:
    def __init__(self, *, bucket: str = BUCKET, s3_key: str = S3_KEY) -> None:
        self._bucket = bucket
        self._s3_key = s3_key
        self._s3 = boto3.client("s3")
        fd, tmp = tempfile.mkstemp(suffix=".db")
        import os

        os.close(fd)
        self._local_path = Path(tmp)

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._local_path)
        for pragma in _PRAGMAS:
            conn.execute(pragma)
        return conn

    def _upload(self) -> None:
        self._s3.upload_file(str(self._local_path), self._bucket, self._s3_key)

    def _download(self) -> None:
        try:
            self._s3.download_file(self._bucket, self._s3_key, str(self._local_path))
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                # No file in S3 yet — start with a fresh empty DB
                conn = self._open()
                conn.execute("CREATE TABLE IF NOT EXISTS seen (uri TEXT PRIMARY KEY)")
                conn.commit()
                conn.close()
            else:
                raise

    def seed(self, uris: list[str]) -> None:
        conn = self._open()
        conn.execute("CREATE TABLE IF NOT EXISTS seen (uri TEXT PRIMARY KEY)")
        conn.executemany("INSERT OR IGNORE INTO seen VALUES (?)", [(u,) for u in uris])
        conn.commit()
        conn.close()
        self._upload()

    def check(self, uris: list[str]) -> tuple[list[str], int]:
        self._download()
        http_calls = 1

        conn = self._open()
        conn.execute("CREATE TABLE IF NOT EXISTS seen (uri TEXT PRIMARY KEY)")
        placeholders = ",".join("?" * len(uris))
        already_seen = {
            row[0]
            for row in conn.execute(f"SELECT uri FROM seen WHERE uri IN ({placeholders})", uris)
        }
        conn.close()

        new_uris = [u for u in uris if u not in already_seen]
        return new_uris, http_calls

    def write(self, uris: list[str]) -> int:
        if not uris:
            return 0
        conn = self._open()
        conn.executemany("INSERT OR IGNORE INTO seen VALUES (?)", [(u,) for u in uris])
        conn.commit()
        conn.close()
        self._upload()
        return 1

    def cleanup(self, uris: list[str]) -> None:
        """Delete the given URIs from the store (reset between benchmark runs)."""
        if not uris:
            return
        self._download()
        conn = self._open()
        placeholders = ",".join("?" * len(uris))
        conn.execute(f"DELETE FROM seen WHERE uri IN ({placeholders})", uris)
        conn.commit()
        conn.close()
        self._upload()

    def clear_all(self) -> None:
        try:
            self._s3.delete_object(Bucket=self._bucket, Key=self._s3_key)
        except Exception:
            pass
        if self._local_path.exists():
            self._local_path.unlink()


def self_check() -> None:
    import os

    if not os.environ.get("AWS_DEFAULT_REGION"):
        print("SKIP: AWS_DEFAULT_REGION not set")
        return

    backend = SQLiteBackend()
    backend.clear_all()
    backend.seed(["at://did:plc:abc/app.bsky.feed.post/001"])

    new_uris, calls = backend.check(
        [
            "at://did:plc:abc/app.bsky.feed.post/001",
            "at://did:plc:abc/app.bsky.feed.post/002",
        ]
    )
    assert new_uris == ["at://did:plc:abc/app.bsky.feed.post/002"], new_uris
    assert calls == 1

    write_calls = backend.write(new_uris)
    assert write_calls == 1

    backend.cleanup(new_uris)
    new_uris2, _ = backend.check(["at://did:plc:abc/app.bsky.feed.post/002"])
    assert new_uris2 == ["at://did:plc:abc/app.bsky.feed.post/002"]

    backend.clear_all()
    print("SQLiteBackend SELF-CHECK PASS")


if __name__ == "__main__":
    self_check()

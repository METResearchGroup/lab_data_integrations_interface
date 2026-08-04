"""The two maintenance operations, and the sweeps that finish what they leave.

``compact_table`` rewrites a table's live data into one file per partition,
collapsing each AT-URI to its latest state and dropping delete tombstones.
``expire_snapshots`` + ``sweep_orphans`` drop old snapshots and then remove the
S3 objects nothing references any more.

PyIceberg 0.11 has no ``rewrite_data_files``, so compaction is implemented as
scan -> collapse -> ``overwrite``, which is a delete-all + append in one commit.

Two things measured here are easy to conflate, so they are counted separately:

- **Redelivered duplicates** -- the same event arriving twice, identified by an
  identical ``(uri, cid)``. These are what "deduplication" normally means. In a
  stable 10-minute Jetstream capture there were *zero* of them.
- **Lifecycle collapses** -- several distinct events about one URI (create then
  delete, create then update), each with its own ``cid``. Collapsing these is a
  state-materialisation decision, not deduplication.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import boto3
import pyarrow as pa
import pyarrow.compute as pc

from experimentation.iceberg import constants


def _collapse_to_latest(table: pa.Table) -> tuple[pa.Table, dict[str, int]]:
    """Reduce each ``uri`` to its most recently ingested row.

    Decomposes what was removed into redelivered duplicates (same ``uri`` *and*
    ``cid``) and lifecycle collapses (same ``uri``, different ``cid``), because
    the two have completely different causes and only the first is a stream
    defect.
    """
    if table.num_rows == 0:
        return table, {"redelivered_duplicates": 0, "lifecycle_collapses": 0}

    # Sort so the surviving row per URI is the newest, then take the first
    # occurrence of each URI.
    sorted_table = table.sort_by([("uri", "ascending"), ("ingested_at", "descending")])
    uris = sorted_table.column("uri").to_pylist()
    cids = sorted_table.column("cid").to_pylist()

    keep_indices: list[int] = []
    previous = object()
    for index, uri in enumerate(uris):
        if uri != previous:
            keep_indices.append(index)
            previous = uri

    distinct_events = len(set(zip(uris, cids, strict=True)))
    stats = {
        # Same URI and same content hash -> the identical event twice.
        "redelivered_duplicates": table.num_rows - distinct_events,
        # Distinct events about one URI -> a record's history.
        "lifecycle_collapses": distinct_events - len(keep_indices),
    }
    return sorted_table.take(pa.array(keep_indices)), stats


def _drop_tombstones(table: pa.Table) -> tuple[pa.Table, int]:
    """Remove ``delete`` rows, which carry no record body.

    Caveat worth knowing: this only reconciles a delete against a create that is
    *in the same table*. A delete of a record written before this table existed
    leaves nothing behind to cancel, and the tombstone is simply discarded.
    """
    if table.num_rows == 0:
        return table, 0
    kept = table.filter(pc.not_equal(table.column("operation"), "delete"))
    return kept, table.num_rows - kept.num_rows


def compact_table(table: Any) -> dict[str, Any]:
    """Compact to one file per partition, collapse each URI, drop tombstones."""
    table.refresh()
    if table.current_snapshot() is None:
        return {"skipped": True}

    files_before = table.inspect.files()
    file_count_before = files_before.num_rows
    bytes_before = sum(files_before.column("file_size_in_bytes").to_pylist())

    scanned = table.scan().to_arrow()
    rows_before = scanned.num_rows

    collapsed, collapse_stats = _collapse_to_latest(scanned)
    final, tombstones = _drop_tombstones(collapsed)

    # overwrite() with no filter is delete-all + append in a single commit --
    # full-table compaction.
    table.overwrite(final)

    table.refresh()
    files_after = table.inspect.files()
    bytes_after = sum(files_after.column("file_size_in_bytes").to_pylist())

    return {
        "skipped": False,
        "file_count_before": file_count_before,
        "file_count_after": files_after.num_rows,
        "bytes_before": bytes_before,
        "bytes_after": bytes_after,
        "rows_before": rows_before,
        "rows_after": final.num_rows,
        "tombstones_dropped": tombstones,
        "tombstone_pct": (tombstones / rows_before * 100) if rows_before else 0.0,
        **collapse_stats,
    }


def expire_snapshots(table: Any) -> dict[str, Any]:
    """Expire every snapshot except the current one.

    ``older_than(now)`` rather than ``by_ids`` so the current snapshot is
    protected by PyIceberg's own retention rules rather than by our bookkeeping.
    """
    table.refresh()
    before = len(table.snapshots())
    if before <= 1:
        return {"snapshots_before": before, "snapshots_after": before, "expired": 0}

    # `older_than` protects the current snapshot itself, so passing "now" expires
    # everything else without us having to track ids.
    table.maintenance.expire_snapshots().older_than(datetime.now(UTC)).commit()

    table.refresh()
    after = len(table.snapshots())
    return {"snapshots_before": before, "snapshots_after": after, "expired": before - after}


def _list_keys(client: Any, prefix: str) -> list[dict[str, Any]]:
    """List every object under ``prefix``, following pagination."""
    keys: list[dict[str, Any]] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=constants.S3_BUCKET, Prefix=prefix):
        keys.extend(page.get("Contents", []))
    return keys


def _delete_keys(client: Any, keys: list[str]) -> int:
    """Batch-delete keys 1000 at a time (the DeleteObjects limit)."""
    deleted = 0
    for start in range(0, len(keys), 1000):
        chunk = keys[start : start + 1000]
        client.delete_objects(
            Bucket=constants.S3_BUCKET,
            Delete={"Objects": [{"Key": key} for key in chunk], "Quiet": True},
        )
        deleted += len(chunk)
    return deleted


def _referenced_paths(table: Any) -> set[str]:
    """Every S3 key the table's live metadata still points at.

    Covers data files plus the manifest and manifest-list chain of all remaining
    snapshots, plus the current and logged ``metadata.json`` files.
    """
    referenced: set[str] = set()

    def add(location: str | None) -> None:
        if location and location.startswith("s3://"):
            referenced.add(location.split("/", 3)[3])

    table.refresh()
    add(table.metadata_location)
    for entry in table.metadata.metadata_log:
        add(entry.metadata_file)

    io = table.io
    for snapshot in table.snapshots():
        add(snapshot.manifest_list)
        try:
            for manifest in snapshot.manifests(io):
                add(manifest.manifest_path)
                for entry in manifest.fetch_manifest_entry(io, discard_deleted=False):
                    add(entry.data_file.file_path)
        except Exception:
            # A manifest list already deleted by expiry is expected here; the
            # sweep just skips whatever it can no longer read.
            continue

    return referenced


def sweep_orphans(table: Any, region: str = constants.AWS_REGION) -> dict[str, Any]:
    """Delete objects under the table prefix that no live metadata references.

    This is the part ``expire_snapshots`` does not do on its own. Counted
    separately so the LIST + DELETE cost of metadata hygiene is visible.
    """
    client = boto3.client("s3", region_name=region)
    location = table.location()
    prefix = location.split("/", 3)[3].rstrip("/") + "/"

    listed = _list_keys(client, prefix)
    referenced = _referenced_paths(table)

    orphans = [obj["Key"] for obj in listed if obj["Key"] not in referenced]
    orphan_bytes = sum(obj["Size"] for obj in listed if obj["Key"] not in referenced)

    deleted = _delete_keys(client, orphans) if orphans else 0

    return {
        "objects_listed": len(listed),
        "objects_referenced": len(referenced),
        "orphans_deleted": deleted,
        "orphan_bytes_reclaimed": orphan_bytes,
    }

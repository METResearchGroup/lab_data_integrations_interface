"""Compare an old `created_at_day` Iceberg file to a current one.

Downloads the two example posts parquet files from the jetstream warehouse,
compares schema / clocks / authors, and optionally inventories year prefixes.

Run from repo root:

    PYTHONPATH=. uv run python -m experiments.jetstream_old_vs_new_posts_2026_08_18.compare
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from experiments.jetstream_old_vs_new_posts_2026_08_18.constants import (
    DATA_DIR,
    DOWNLOAD_DIR,
    NEW_KEY,
    OLD_KEY,
    POSTS_DATA_PREFIX,
    S3_BUCKET,
)
from experiments.jetstream_old_vs_new_posts_2026_08_18.profiles import fetch_profiles
from experiments.jetstream_old_vs_new_posts_2026_08_18.s3_io import (
    download_key,
    inventory_years,
    list_parquet_keys,
    s3_client,
)
from experiments.jetstream_old_vs_new_posts_2026_08_18.tid import rkey_from_uri, tid_datetime

SECONDS_PER_DAY = 86400.0


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, float) and value != value:  # NaN
        return None
    return value


def _describe_seconds(series: pd.Series) -> dict[str, float | None]:
    if series.empty:
        return {}
    desc = series.describe()
    return {
        "count": int(desc["count"]),
        "mean": float(desc["mean"]),
        "std": None if pd.isna(desc["std"]) else float(desc["std"]),
        "min": float(desc["min"]),
        "p25": float(desc["25%"]),
        "p50": float(desc["50%"]),
        "p75": float(desc["75%"]),
        "max": float(desc["max"]),
    }


def file_schema_report(path: Path) -> dict[str, Any]:
    parquet_file = pq.ParquetFile(path)
    schema = parquet_file.schema_arrow
    return {
        "path": str(path),
        "num_rows": parquet_file.metadata.num_rows,
        "num_row_groups": parquet_file.num_row_groups,
        "created_by": parquet_file.metadata.created_by,
        "format_version": parquet_file.metadata.format_version,
        "columns": [
            {
                "name": field.name,
                "type": str(field.type),
                "field_id": (field.metadata or {}).get(b"PARQUET:field_id", b"").decode(),
            }
            for field in schema
        ],
    }


def attach_tids(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["rkey"] = out["uri"].map(rkey_from_uri)
    out["rkey_tid_at"] = out["rkey"].map(tid_datetime)
    out["rev_tid_at"] = out["rev"].map(tid_datetime)
    return out


def summarize_frame(label: str, frame: pd.DataFrame, object_meta: dict[str, Any]) -> dict[str, Any]:
    frame = attach_tids(frame)
    ingest_lag_s = (frame["ingested_at"] - frame["created_at"]).dt.total_seconds()
    rkey_vs_created_s = (frame["rkey_tid_at"] - frame["created_at"]).dt.total_seconds()
    rev_vs_ingested_s = (frame["ingested_at"] - frame["rev_tid_at"]).dt.total_seconds()

    embed_counts = frame["embed_type"].fillna("<null>").value_counts().to_dict()
    run_ids = frame["run_id"].value_counts().to_dict()
    did_counts = frame["did"].value_counts()

    return {
        "label": label,
        "s3": object_meta,
        "n_rows": int(len(frame)),
        "n_unique_uri": int(frame["uri"].nunique()),
        "n_unique_did": int(frame["did"].nunique()),
        "run_ids": {str(key): int(value) for key, value in run_ids.items()},
        "created_at_min": _json_ready(frame["created_at"].min()),
        "created_at_max": _json_ready(frame["created_at"].max()),
        "ingested_at_min": _json_ready(frame["ingested_at"].min()),
        "ingested_at_max": _json_ready(frame["ingested_at"].max()),
        "ingest_lag_seconds": _describe_seconds(ingest_lag_s),
        "ingest_lag_days": _describe_seconds(ingest_lag_s / SECONDS_PER_DAY),
        "rkey_tid_minus_created_seconds": _describe_seconds(rkey_vs_created_s),
        "ingested_minus_rev_tid_seconds": _describe_seconds(rev_vs_ingested_s),
        "rkey_tid_equals_created_at_rate": float((rkey_vs_created_s.abs() < 1).mean()),
        "null_rates": {col: float(frame[col].isna().mean()) for col in frame.columns if col in (
            "langs",
            "reply_root_uri",
            "reply_parent_uri",
            "embed_type",
            "text",
        )},
        "reply_rate": float(frame["reply_parent_uri"].notna().mean()),
        "embed_type_counts": {str(key): int(value) for key, value in embed_counts.items()},
        "text_length": _describe_seconds(frame["text"].fillna("").str.len().astype(float)),
        "top_dids": [
            {"did": str(did), "n_rows": int(count)} for did, count in did_counts.head(10).items()
        ],
        "sample_rows": [
            {
                "uri": row.uri,
                "did": row.did,
                "rev": row.rev,
                "created_at": _json_ready(row.created_at),
                "ingested_at": _json_ready(row.ingested_at),
                "rkey_tid_at": _json_ready(row.rkey_tid_at),
                "rev_tid_at": _json_ready(row.rev_tid_at),
                "embed_type": row.embed_type,
                "text": row.text,
            }
            for row in frame.head(8).itertuples(index=False)
        ],
    }


def compare_schemas(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    old_cols = [(col["name"], col["type"], col["field_id"]) for col in old["columns"]]
    new_cols = [(col["name"], col["type"], col["field_id"]) for col in new["columns"]]
    return {
        "identical": old_cols == new_cols,
        "old_created_by": old["created_by"],
        "new_created_by": new["created_by"],
        "old_columns": old["columns"],
        "new_columns": new["columns"],
    }


def sample_old_year(
    client: Any,
    year: int,
    n_files: int,
    seed: int,
) -> dict[str, Any]:
    prefix = f"{POSTS_DATA_PREFIX}created_at_day={year}-"
    keys = list_parquet_keys(client, prefix)
    rng = random.Random(seed)
    sample = keys if len(keys) <= n_files else rng.sample(keys, n_files)

    did_counter: Counter[str] = Counter()
    embed_counter: Counter[str] = Counter()
    n_rows = 0
    n_replies = 0
    n_langs_null = 0
    run_ids: Counter[str] = Counter()
    per_file: list[dict[str, Any]] = []

    for key in sample:
        dest = DOWNLOAD_DIR / "sample" / Path(key).name
        meta = download_key(client, key, dest)
        frame = pq.read_table(dest).to_pandas()
        n_rows += len(frame)
        did_counter.update(frame["did"].tolist())
        embed_counter.update(frame["embed_type"].fillna("<null>").tolist())
        n_replies += int(frame["reply_parent_uri"].notna().sum())
        n_langs_null += int(frame["langs"].isna().sum())
        run_ids.update(frame["run_id"].tolist())
        per_file.append(
            {
                "key": key,
                "n_rows": int(len(frame)),
                "n_unique_did": int(frame["did"].nunique()),
                "bytes": meta["bytes"],
                "ingested_at_min": _json_ready(frame["ingested_at"].min()),
                "ingested_at_max": _json_ready(frame["ingested_at"].max()),
            }
        )

    return {
        "year": year,
        "n_files_listed": len(keys),
        "n_files_sampled": len(sample),
        "n_rows": n_rows,
        "reply_rate": (n_replies / n_rows) if n_rows else None,
        "langs_null_rate": (n_langs_null / n_rows) if n_rows else None,
        "embed_type_counts": dict(embed_counter),
        "run_ids": dict(run_ids),
        "top_dids": [{"did": did, "n_rows": count} for did, count in did_counter.most_common(10)],
        "files": per_file,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-key", default=OLD_KEY)
    parser.add_argument("--new-key", default=NEW_KEY)
    parser.add_argument("--skip-inventory", action="store_true")
    parser.add_argument("--skip-profiles", action="store_true")
    parser.add_argument("--sample-old-year", type=int, default=2022)
    parser.add_argument("--sample-files", type=int, default=15)
    parser.add_argument("--skip-sample", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    client = s3_client()

    old_meta = download_key(client, args.old_key, DOWNLOAD_DIR / "old.parquet")
    new_meta = download_key(client, args.new_key, DOWNLOAD_DIR / "new.parquet")

    old_path = Path(old_meta["local_path"])
    new_path = Path(new_meta["local_path"])
    old_schema = file_schema_report(old_path)
    new_schema = file_schema_report(new_path)
    old_frame = pq.read_table(old_path).to_pandas()
    new_frame = pq.read_table(new_path).to_pandas()

    old_summary = summarize_frame("old", old_frame, old_meta)
    new_summary = summarize_frame("new", new_frame, new_meta)

    report: dict[str, Any] = {
        "bucket": S3_BUCKET,
        "schema_comparison": compare_schemas(old_schema, new_schema),
        "old": old_summary,
        "new": new_summary,
    }

    if not args.skip_inventory:
        report["year_inventory"] = inventory_years(client)

    if not args.skip_sample:
        report["old_year_sample"] = sample_old_year(
            client, args.sample_old_year, args.sample_files, seed=0
        )

    profile_dids = [item["did"] for item in old_summary["top_dids"]]
    if not args.skip_sample:
        profile_dids.extend(item["did"] for item in report["old_year_sample"]["top_dids"])
    # unique, preserve order
    seen: set[str] = set()
    unique_dids = []
    for did in profile_dids:
        if did not in seen:
            seen.add(did)
            unique_dids.append(did)

    if not args.skip_profiles:
        report["author_profiles"] = fetch_profiles(unique_dids[:12])

    out_path = DATA_DIR / "comparison.json"
    out_path.write_text(json.dumps(_json_ready(report), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out_path}")
    print(json.dumps(_json_ready({
        "schema_identical": report["schema_comparison"]["identical"],
        "old_rows": old_summary["n_rows"],
        "new_rows": new_summary["n_rows"],
        "old_ingest_lag_days_mean": old_summary["ingest_lag_days"].get("mean"),
        "new_ingest_lag_days_mean": new_summary["ingest_lag_days"].get("mean"),
        "old_rkey_matches_created_at": old_summary["rkey_tid_equals_created_at_rate"],
        "year_inventory": report.get("year_inventory"),
        "author_profiles": [
            {k: p.get(k) for k in ("did", "handle", "displayName", "createdAt", "postsCount")}
            for p in report.get("author_profiles", [])
        ],
    }), indent=2))


if __name__ == "__main__":
    main()

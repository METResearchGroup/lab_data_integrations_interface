"""Tests for the metering layer -- key classification, billing tiers, attribution."""

from __future__ import annotations

import io
import threading

from experimentation.iceberg import constants
from experimentation.iceberg.s3_meter import (
    KEY_CLASS_DATA,
    KEY_CLASS_MANIFEST,
    KEY_CLASS_MANIFEST_LIST,
    KEY_CLASS_METADATA_JSON,
    KEY_CLASS_OTHER,
    KEY_CLASS_RAW,
    Meter,
    _body_size,
    _extract_key,
    classify_key,
    cost_tier,
)

BUCKET = "lab-data-integrations-interface"


class TestClassifyKey:
    def test_metadata_json(self):
        key = "experiments/iceberg/run1/warehouse/posts/metadata/00003-abc.metadata.json"
        assert classify_key(key) == KEY_CLASS_METADATA_JSON

    def test_manifest_list_beats_generic_avro(self):
        key = "experiments/iceberg/run1/warehouse/posts/metadata/snap-123-1-abc.avro"
        assert classify_key(key) == KEY_CLASS_MANIFEST_LIST

    def test_manifest(self):
        key = "experiments/iceberg/run1/warehouse/posts/metadata/abc-m0.avro"
        assert classify_key(key) == KEY_CLASS_MANIFEST

    def test_data_file(self):
        key = "experiments/iceberg/run1/warehouse/posts/data/created_at_day=2026-07-22/x.parquet"
        assert classify_key(key) == KEY_CLASS_DATA

    def test_raw_baseline_is_not_counted_as_iceberg_data(self):
        key = "experiments/iceberg/run1/raw/posts/created_at_day=2026-07-22/batch-00001.parquet"
        assert classify_key(key) == KEY_CLASS_RAW

    def test_empty_key(self):
        assert classify_key("") == KEY_CLASS_OTHER


class TestCostTier:
    def test_put_operations(self):
        assert cost_tier("s3", "PutObject") == "put"
        assert cost_tier("s3", "ListObjectsV2") == "put"
        assert cost_tier("s3", "CompleteMultipartUpload") == "put"

    def test_get_is_the_fallback(self):
        assert cost_tier("s3", "GetObject") == "get"
        assert cost_tier("s3", "HeadObject") == "get"

    def test_delete_is_free(self):
        assert cost_tier("s3", "DeleteObject") == "delete"
        assert cost_tier("s3", "DeleteObjects") == "delete"

    def test_glue_is_its_own_tier(self):
        assert cost_tier("glue", "UpdateTable") == "glue"


class TestExtractKey:
    def test_virtual_hosted_style(self):
        url = f"https://{BUCKET}.s3.us-east-2.amazonaws.com/experiments/iceberg/a/b.parquet"
        assert _extract_key(url, BUCKET) == "experiments/iceberg/a/b.parquet"

    def test_path_style_strips_bucket(self):
        url = f"https://s3.us-east-2.amazonaws.com/{BUCKET}/experiments/iceberg/a/b.parquet"
        assert _extract_key(url, BUCKET) == "experiments/iceberg/a/b.parquet"

    def test_bucket_root(self):
        assert _extract_key(f"https://s3.us-east-2.amazonaws.com/{BUCKET}", BUCKET) == ""

    def test_percent_encoded_key_is_decoded(self):
        url = f"https://{BUCKET}.s3.us-east-2.amazonaws.com/a/created_at_day%3D2026-07-22/x.parquet"
        assert _extract_key(url, BUCKET) == "a/created_at_day=2026-07-22/x.parquet"


class TestBodySize:
    """botocore hands us a BytesIO with no Content-Length; sizing must still work."""

    def test_bytes_body(self):
        assert _body_size(b"A" * 4096) == 4096

    def test_str_body_is_measured_in_utf8_bytes(self):
        assert _body_size("é" * 10) == 20

    def test_bytesio_body(self):
        assert _body_size(io.BytesIO(b"A" * 4096)) == 4096

    def test_bytesio_position_is_restored(self):
        """Consuming the stream here would corrupt the upload."""
        body = io.BytesIO(b"A" * 4096)
        body.seek(100)
        assert _body_size(body) == 3996
        assert body.tell() == 100

    def test_none_and_unmeasurable_bodies(self):
        assert _body_size(None) == 0
        assert _body_size(object()) == 0

    def test_chunked_upload_falls_back_to_decoded_length_header(self):
        """Large uploads switch to aws-chunked and drop Content-Length entirely."""
        meter = Meter(bucket=BUCKET)
        context: dict = {}
        params = {
            "url": f"https://{BUCKET}.s3.us-east-2.amazonaws.com/w/posts/data/x.parquet",
            "headers": {
                "X-Amz-Decoded-Content-Length": b"8388608",
                "Transfer-Encoding": b"chunked",
            },
            "body": None,
        }
        meter._on_before_call(params=params, context=context)
        assert context["_iceberg_meter_request_bytes"] == 8_388_608


def _record_call(meter: Meter, operation: str, key: str, service: str = "s3") -> None:
    """Drive the meter's handlers the way botocore would."""
    context: dict = {}
    model = type(
        "Model",
        (),
        {"name": operation, "service_model": type("SM", (), {"endpoint_prefix": service})()},
    )()
    params = {
        "url": f"https://{BUCKET}.s3.us-east-2.amazonaws.com/{key}",
        "headers": {"Content-Length": "100"},
    }
    meter._on_before_call(params=params, context=context)
    response = type("Resp", (), {"status_code": 200, "headers": {"Content-Length": "250"}})()
    meter._on_after_call(http_response=response, model=model, context=context)


class TestPhaseAttribution:
    def test_calls_land_in_the_active_phase(self):
        meter = Meter(bucket=BUCKET)
        with meter.phase(constants.PHASE_ICEBERG_APPEND):
            _record_call(meter, "PutObject", "w/posts/data/x.parquet")
        with meter.phase(constants.PHASE_COMPACT_DEDUP):
            _record_call(meter, "GetObject", "w/posts/data/x.parquet")

        stats = meter.summarize()
        assert stats[constants.PHASE_ICEBERG_APPEND].by_tier["put"] == 1
        assert stats[constants.PHASE_COMPACT_DEDUP].by_tier["get"] == 1

    def test_nested_phases_restore_the_outer_phase(self):
        meter = Meter(bucket=BUCKET)
        with meter.phase("outer"):
            with meter.phase("inner"):
                pass
            assert meter.current_phase == "outer"
        assert meter.current_phase == "unattributed"

    def test_bytes_and_key_class_are_recorded(self):
        meter = Meter(bucket=BUCKET)
        with meter.phase(constants.PHASE_ICEBERG_APPEND):
            _record_call(meter, "PutObject", "w/posts/metadata/00001-a.metadata.json")

        stats = meter.summarize()[constants.PHASE_ICEBERG_APPEND]
        assert stats.request_bytes == 100
        assert stats.response_bytes == 250
        assert stats.by_key_class[KEY_CLASS_METADATA_JSON] == 1

    def test_concurrent_calls_are_all_counted(self):
        """PyIceberg writes manifests from a thread pool; the counters must hold."""
        meter = Meter(bucket=BUCKET)
        with meter.phase(constants.PHASE_ICEBERG_APPEND):
            threads = [
                threading.Thread(
                    target=_record_call, args=(meter, "PutObject", f"w/posts/data/{i}.parquet")
                )
                for i in range(50)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        assert meter.summarize()[constants.PHASE_ICEBERG_APPEND].calls == 50

    def test_retries_show_up_as_attempts_above_calls(self):
        meter = Meter(bucket=BUCKET)
        with meter.phase(constants.PHASE_ICEBERG_APPEND):
            _record_call(meter, "PutObject", "w/posts/data/x.parquet")
            meter._on_before_send()
            meter._on_before_send()

        stats = meter.summarize()[constants.PHASE_ICEBERG_APPEND]
        assert stats.calls == 1
        assert stats.attempts == 2


class TestCostModel:
    def test_cost_uses_the_right_rate_per_tier(self):
        meter = Meter(bucket=BUCKET)
        with meter.phase(constants.PHASE_ICEBERG_APPEND):
            for i in range(1000):
                _record_call(meter, "PutObject", f"w/posts/data/{i}.parquet")
            for i in range(1000):
                _record_call(meter, "GetObject", f"w/posts/data/{i}.parquet")
            _record_call(meter, "UpdateTable", "", service="glue")

        stats = meter.summarize()[constants.PHASE_ICEBERG_APPEND]
        expected = 0.005 + 0.0004 + constants.COST_PER_GLUE_REQUEST
        assert abs(stats.cost_usd - expected) < 1e-9

    def test_deletes_are_free(self):
        meter = Meter(bucket=BUCKET)
        with meter.phase(constants.PHASE_EXPIRE_METADATA):
            for i in range(500):
                _record_call(meter, "DeleteObject", f"w/posts/data/{i}.parquet")

        assert meter.summarize()[constants.PHASE_EXPIRE_METADATA].cost_usd == 0.0

    def test_percentiles(self):
        meter = Meter(bucket=BUCKET)
        with meter.phase("p"):
            _record_call(meter, "PutObject", "a.parquet")
        stats = meter.summarize()["p"]
        stats.latencies_ms = [float(i) for i in range(1, 101)]
        assert stats.percentile(50) == 50.0
        assert stats.percentile(95) == 95.0

    def test_percentile_of_empty_is_zero(self):
        from experimentation.iceberg.s3_meter import PhaseStats

        assert PhaseStats(phase="x").percentile(95) == 0.0

from __future__ import annotations

import os

os.environ.setdefault("PREFECT_SERVER_ALLOW_EPHEMERAL_MODE", "true")
os.environ.setdefault("PREFECT_API_URL", "")

import logging
from pathlib import Path
from typing import Any
from unittest.mock import ANY

import pytest

from data_platform.orchestration import orchestrate_bluesky as orch
from tests.data_platform.constants import VALID_DATASET_ID

INGESTION_CONFIG = Path("ingestion.yaml")
CURATE_CONFIG = Path("curate.yaml")


@pytest.fixture(autouse=True)
def fake_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orch, "resolve_config_path", lambda path, _base_dir: path)
    monkeypatch.setattr(orch, "load_yaml_config", lambda _path: {"dataset_id": VALID_DATASET_ID})


@pytest.fixture
def recorded_calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    calls: dict[str, list[Any]] = {"init": [], "stage": [], "finalize": []}

    def fake_new_pipeline_run_id() -> str:
        return "fixed-run-id"

    def fake_init(pipeline_run_id: str, dataset_id: str, _started_at: str) -> None:
        calls["init"].append((pipeline_run_id, dataset_id))

    def fake_record_stage_result(
        pipeline_run_id: str,
        stage: str,
        *,
        run_id: str | None,
        status: str,
        error: str | None = None,
    ) -> None:
        calls["stage"].append(
            {
                "pipeline_run_id": pipeline_run_id,
                "stage": stage,
                "run_id": run_id,
                "status": status,
                "error": error,
            }
        )

    def fake_finalize(pipeline_run_id: str, *, status: str, completed_at: str) -> None:
        calls["finalize"].append(
            {"pipeline_run_id": pipeline_run_id, "status": status, "completed_at": completed_at}
        )

    monkeypatch.setattr(orch, "new_pipeline_run_id", fake_new_pipeline_run_id)
    monkeypatch.setattr(orch, "init_pipeline_run", fake_init)
    monkeypatch.setattr(orch, "record_stage_result", fake_record_stage_result)
    monkeypatch.setattr(orch, "finalize_pipeline_run", fake_finalize)
    return calls


def test_full_success_records_each_stage_and_finalizes_completed(
    monkeypatch: pytest.MonkeyPatch, recorded_calls: dict[str, list[Any]]
) -> None:
    monkeypatch.setattr(orch, "sync_records", lambda _cfg: Path("raw/2026_01_01-00:00:00"))
    monkeypatch.setattr(
        orch, "preprocess_records", lambda _dataset_id: Path("preprocessed/2026_01_01-00:05:00")
    )
    monkeypatch.setattr(
        orch,
        "generate_bluesky_features",
        lambda _dataset_id: {"is_political": Path("features/is_political.csv")},
    )
    monkeypatch.setattr(
        orch, "curate_bluesky", lambda _cfg, _dataset_id: Path("curated/2026_01_01-00:10:00")
    )

    orch.orchestrate_bluesky(INGESTION_CONFIG, CURATE_CONFIG)

    assert recorded_calls["init"] == [("fixed-run-id", VALID_DATASET_ID)]

    stages = recorded_calls["stage"]
    assert [s["stage"] for s in stages] == ["ingestion", "preprocessing", "features", "curation"]
    assert [s["status"] for s in stages] == ["completed"] * 4
    assert [s["run_id"] for s in stages] == [
        "2026_01_01-00:00:00",
        "2026_01_01-00:05:00",
        None,
        "2026_01_01-00:10:00",
    ]
    assert recorded_calls["finalize"] == [
        {"pipeline_run_id": "fixed-run-id", "status": "completed", "completed_at": ANY}
    ]


def test_stage_failure_stops_pipeline_and_marks_failed(
    monkeypatch: pytest.MonkeyPatch, recorded_calls: dict[str, list[Any]]
) -> None:
    called: list[str] = []

    def fake_sync(_cfg: Path) -> Path:
        called.append("ingestion")
        return Path("raw/2026_01_01-00:00:00")

    def fake_preprocess(_dataset_id: str) -> Path:
        called.append("preprocessing")
        return Path("preprocessed/2026_01_01-00:05:00")

    def fake_features(_dataset_id: str) -> dict[str, Path]:
        called.append("features")
        raise RuntimeError("Claude API timeout")

    def fake_curate(_cfg: Path, _dataset_id: str) -> Path:
        called.append("curation")
        return Path("curated/2026_01_01-00:10:00")

    monkeypatch.setattr(orch, "sync_records", fake_sync)
    monkeypatch.setattr(orch, "preprocess_records", fake_preprocess)
    monkeypatch.setattr(orch, "generate_bluesky_features", fake_features)
    monkeypatch.setattr(orch, "curate_bluesky", fake_curate)

    with pytest.raises(RuntimeError, match="Claude API timeout"):
        orch.orchestrate_bluesky(INGESTION_CONFIG, CURATE_CONFIG)

    assert called == ["ingestion", "preprocessing", "features"]

    stages = recorded_calls["stage"]
    assert [s["stage"] for s in stages] == ["ingestion", "preprocessing", "features"]
    assert stages[-1] == {
        "pipeline_run_id": "fixed-run-id",
        "stage": "features",
        "run_id": None,
        "status": "failed",
        "error": "Claude API timeout",
    }
    assert recorded_calls["finalize"] == [
        {"pipeline_run_id": "fixed-run-id", "status": "failed", "completed_at": ANY}
    ]


def test_init_pipeline_run_receives_dataset_id_and_a_real_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, str]] = []

    def fake_init(pipeline_run_id: str, dataset_id: str, started_at: str) -> None:
        calls.append((pipeline_run_id, dataset_id, started_at))

    monkeypatch.setattr(orch, "new_pipeline_run_id", lambda: "fixed-run-id")
    monkeypatch.setattr(orch, "init_pipeline_run", fake_init)
    monkeypatch.setattr(orch, "record_stage_result", lambda *_a, **_k: None)
    monkeypatch.setattr(orch, "finalize_pipeline_run", lambda *_a, **_k: None)
    monkeypatch.setattr(orch, "sync_records", lambda _cfg: Path("raw/2026_01_01-00:00:00"))
    monkeypatch.setattr(
        orch, "preprocess_records", lambda _dataset_id: Path("preprocessed/2026_01_01-00:05:00")
    )
    monkeypatch.setattr(orch, "generate_bluesky_features", lambda _dataset_id: {})
    monkeypatch.setattr(
        orch, "curate_bluesky", lambda _cfg, _dataset_id: Path("curated/2026_01_01-00:10:00")
    )

    orch.orchestrate_bluesky(INGESTION_CONFIG, CURATE_CONFIG)

    # called exactly once, before any stage, with the real dataset id and a non-empty
    # timestamp (not silently dropped or left as None/blank)
    assert len(calls) == 1
    pipeline_run_id, dataset_id, started_at = calls[0]
    assert pipeline_run_id == "fixed-run-id"
    assert dataset_id == VALID_DATASET_ID
    assert isinstance(started_at, str) and started_at != ""


def test_record_stage_result_failure_on_success_path_is_logged_not_raised(
    monkeypatch: pytest.MonkeyPatch,
    recorded_calls: dict[str, list[Any]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A DynamoDB write failure while recording a 'completed' stage must not crash the
    flow or block later stages -- this is what _record_best_effort guards against."""
    called: list[str] = []

    def fake_sync(_cfg: Path) -> Path:
        called.append("ingestion")
        return Path("raw/2026_01_01-00:00:00")

    def fake_preprocess(_dataset_id: str) -> Path:
        called.append("preprocessing")
        return Path("preprocessed/2026_01_01-00:05:00")

    def fake_features(_dataset_id: str) -> dict[str, Path]:
        called.append("features")
        return {}

    def fake_curate(_cfg: Path, _dataset_id: str) -> Path:
        called.append("curation")
        return Path("curated/2026_01_01-00:10:00")

    monkeypatch.setattr(orch, "sync_records", fake_sync)
    monkeypatch.setattr(orch, "preprocess_records", fake_preprocess)
    monkeypatch.setattr(orch, "generate_bluesky_features", fake_features)
    monkeypatch.setattr(orch, "curate_bluesky", fake_curate)

    def flaky_record_stage_result(
        pipeline_run_id: str,
        stage: str,
        *,
        run_id: str | None,
        status: str,
        error: str | None = None,
    ) -> None:
        if stage == "ingestion":
            raise RuntimeError("dynamo throttled")
        recorded_calls["stage"].append(
            {
                "pipeline_run_id": pipeline_run_id,
                "stage": stage,
                "run_id": run_id,
                "status": status,
                "error": error,
            }
        )

    monkeypatch.setattr(orch, "record_stage_result", flaky_record_stage_result)

    with caplog.at_level(logging.ERROR, logger="data_platform.orchestration.orchestrate_bluesky"):
        orch.orchestrate_bluesky(INGESTION_CONFIG, CURATE_CONFIG)

    # every stage still ran despite the ingestion stage's write failing
    assert called == ["ingestion", "preprocessing", "features", "curation"]
    # the failed write was logged, not allowed to raise
    assert "Failed to record pipeline run state" in caplog.text
    # remaining stages' writes still went through normally
    assert [s["stage"] for s in recorded_calls["stage"]] == [
        "preprocessing",
        "features",
        "curation",
    ]
    # one bad write doesn't sour the overall run
    assert recorded_calls["finalize"] == [
        {"pipeline_run_id": "fixed-run-id", "status": "completed", "completed_at": ANY}
    ]


def test_record_stage_result_failure_on_failure_path_does_not_mask_original_exception(
    monkeypatch: pytest.MonkeyPatch,
    recorded_calls: dict[str, list[Any]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """If record_stage_result raises while recording a stage failure, the real stage
    exception must still propagate (not replaced by the DynamoDB error), and
    finalize_pipeline_run must still be attempted."""

    def fake_sync(_cfg: Path) -> Path:
        return Path("raw/2026_01_01-00:00:00")

    def fake_preprocess(_dataset_id: str) -> Path:
        raise RuntimeError("preprocessing exploded")

    monkeypatch.setattr(orch, "sync_records", fake_sync)
    monkeypatch.setattr(orch, "preprocess_records", fake_preprocess)

    def flaky_record_stage_result(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("dynamo throttled")

    monkeypatch.setattr(orch, "record_stage_result", flaky_record_stage_result)

    with caplog.at_level(logging.ERROR, logger="data_platform.orchestration.orchestrate_bluesky"):
        with pytest.raises(RuntimeError, match="preprocessing exploded"):
            orch.orchestrate_bluesky(INGESTION_CONFIG, CURATE_CONFIG)

    # the DynamoDB write failure(s) were logged, not raised
    assert "Failed to record pipeline run state" in caplog.text
    # finalize_pipeline_run still ran despite record_stage_result failing
    assert recorded_calls["finalize"] == [
        {"pipeline_run_id": "fixed-run-id", "status": "failed", "completed_at": ANY}
    ]

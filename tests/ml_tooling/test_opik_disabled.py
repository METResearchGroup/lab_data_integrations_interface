from __future__ import annotations

from ml_tooling.llm import opik as opik_telemetry


def test_set_opik_enabled_disables_callbacks_and_flush() -> None:
    opik_telemetry.set_opik_enabled(False)
    assert opik_telemetry.langchain_callbacks(feature_name="test") == []
    opik_telemetry.enrich_llm_trace(input={"x": 1})
    opik_telemetry.flush()
    opik_telemetry.set_opik_enabled(True)


def test_track_llm_call_noop_when_disabled() -> None:
    opik_telemetry.set_opik_enabled(False)

    @opik_telemetry.track_llm_call(name="test_fn")
    def sample(x: int) -> int:
        return x + 1

    assert sample(1) == 2
    opik_telemetry.set_opik_enabled(True)

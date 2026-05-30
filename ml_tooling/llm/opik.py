"""Opik telemetry for LLM calls: tracing, prompt registry, and LangChain integration."""

from __future__ import annotations

import contextlib
import contextvars
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

import opik

PROJECT_NAME = "lab_data_integrations_interface"

opik.configure(
    use_local=False,
    project_name=PROJECT_NAME,
    automatic_approvals=True,
)

_feature_context: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "opik_feature_context",
    default={},
)


def push_context(**fields: Any) -> contextvars.Token[dict[str, Any]]:
    """Push feature-generation context for the current record."""
    merged = {**_feature_context.get(), **fields}
    return _feature_context.set(merged)


def pop_context(token: contextvars.Token[dict[str, Any]]) -> None:
    """Restore the previous feature-generation context."""
    _feature_context.reset(token)


def current_context() -> dict[str, Any]:
    """Return the active feature-generation context."""
    return dict(_feature_context.get())


def enrich_llm_trace(**kwargs: Any) -> None:
    """Update the current Opik trace; kwargs are forwarded to ``update_current_trace``."""
    from opik import opik_context

    opik_context.update_current_trace(**kwargs)


@lru_cache(maxsize=64)
def resolve_system_prompt(*, feature_name: str, system_prompt: str) -> Any:
    """Register or resolve a versioned system prompt in the Opik prompt library."""
    return opik.get_global_client().create_prompt(
        name=feature_name,
        prompt=system_prompt,
        project_name=PROJECT_NAME,
    )


def langchain_callbacks(*, feature_name: str | None = None) -> list[Any]:
    """Build LangChain callback handlers for Opik tracing."""
    from opik.integrations.langchain import OpikTracer

    tags = [feature_name] if feature_name else None
    return [OpikTracer(tags=tags)]


def flush() -> None:
    """Flush pending Opik traces to the server."""
    opik.flush_tracker()


def utc_now_iso() -> str:
    """Return the current UTC timestamp as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


def track_llm_call(name: str):
    """Return an ``@opik.track`` decorator for LLM entrypoints."""
    return opik.track(
        name=name,
        project_name=PROJECT_NAME,
        ignore_arguments=["output_schema", "system_prompt"],
    )


@contextlib.contextmanager
def project_scope():
    """Scope all Opik operations in a batch to ``PROJECT_NAME``."""
    with opik.project_context(PROJECT_NAME):
        yield

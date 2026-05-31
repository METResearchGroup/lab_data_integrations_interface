"""Opik telemetry for LLM calls: tracing, prompt registry, and LangChain integration."""

from __future__ import annotations

import contextlib
import contextvars
from collections.abc import Callable
from functools import lru_cache, wraps
from typing import Any, TypeVar

import opik

PROJECT_NAME = "lab_data_integrations_interface"

_configured = False

_opik_enabled: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "opik_enabled",
    default=True,
)

_feature_context: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "opik_feature_context",
    default={},
)

F = TypeVar("F", bound=Callable[..., Any])


def _ensure_configured() -> None:
    """Configure Opik once when telemetry is enabled."""
    global _configured
    if _configured or not is_opik_enabled():
        return
    opik.configure(
        use_local=False,
        project_name=PROJECT_NAME,
        automatic_approvals=True,
    )
    _configured = True


def set_opik_enabled(enabled: bool) -> None:
    """Enable or disable Opik telemetry for the current context."""
    _opik_enabled.set(enabled)


def is_opik_enabled() -> bool:
    """Return whether Opik tracing is enabled in the current context."""
    return _opik_enabled.get()


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
    if not is_opik_enabled():
        return
    _ensure_configured()
    from opik import opik_context

    opik_context.update_current_trace(**kwargs)


@lru_cache(maxsize=64)
def resolve_system_prompt(*, feature_name: str, system_prompt: str) -> Any:
    """Register or resolve a versioned system prompt in the Opik prompt library."""
    if not is_opik_enabled():
        return system_prompt
    _ensure_configured()
    return opik.get_global_client().create_prompt(
        name=feature_name,
        prompt=system_prompt,
        project_name=PROJECT_NAME,
    )


def langchain_callbacks(*, feature_name: str | None = None) -> list[Any]:
    """Build LangChain callback handlers for Opik tracing."""
    if not is_opik_enabled():
        return []
    _ensure_configured()
    from opik.integrations.langchain import OpikTracer

    tags = [feature_name] if feature_name else None
    return [OpikTracer(tags=tags)]


def flush() -> None:
    """Flush pending Opik traces to the server."""
    if not is_opik_enabled():
        return
    _ensure_configured()
    opik.flush_tracker()


def track_llm_call(name: str) -> Callable[[F], F]:
    """Return an ``@opik.track`` decorator for LLM entrypoints, or a no-op when disabled."""
    tracked_fn: dict[str, Callable[..., Any]] = {}

    def decorator(fn: F) -> F:
        if is_opik_enabled():
            _ensure_configured()
            tracked_fn["impl"] = opik.track(
                name=name,
                project_name=PROJECT_NAME,
                ignore_arguments=["output_schema", "system_prompt"],
            )(fn)

        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if is_opik_enabled() and "impl" in tracked_fn:
                return tracked_fn["impl"](*args, **kwargs)
            return fn(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


@contextlib.contextmanager
def project_scope():
    """Scope all Opik operations in a batch to ``PROJECT_NAME``."""
    if not is_opik_enabled():
        yield
        return
    _ensure_configured()
    with opik.project_context(PROJECT_NAME):
        yield

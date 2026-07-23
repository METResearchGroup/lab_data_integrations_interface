"""Per-call S3 and Glue instrumentation.

The whole experiment hangs off this module. PyIceberg's default ``PyArrowFileIO``
drives a C++ S3 client that cannot be intercepted from Python, so the experiment
configures ``FsspecFileIO`` instead: s3fs -> aiobotocore -> botocore, which means
every request passes through botocore's event system where we can count it.

Registration works by wrapping ``botocore.session.Session.__init__`` so that
*every* session -- boto3's for raw writes, aiobotocore's inside s3fs, and the
Glue client PyIceberg builds for catalog commits -- gets the handlers. Install
the meter before creating any client.

Counting happens at ``before-call``/``after-call``, i.e. once per logical API
operation. ``before-send`` fires once per HTTP attempt, so ``attempts`` exceeding
``calls`` is the retry signal.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote, urlparse

import botocore.session

from experimentation.iceberg import constants

# Object classes we bucket S3 keys into. The Iceberg metadata tree is the whole
# point of the experiment, so it gets three separate buckets.
KEY_CLASS_DATA = "data"
KEY_CLASS_MANIFEST = "manifest"
KEY_CLASS_MANIFEST_LIST = "manifest-list"
KEY_CLASS_METADATA_JSON = "metadata-json"
KEY_CLASS_RAW = "raw"
KEY_CLASS_OTHER = "other"

_UNSET_PHASE = "unattributed"


def classify_key(key: str) -> str:
    """Bucket an S3 object key into one of the KEY_CLASS_* constants."""
    if not key:
        return KEY_CLASS_OTHER

    tail = key.rsplit("/", 1)[-1]

    if "/metadata/" in key or key.startswith("metadata/"):
        if tail.endswith(".metadata.json"):
            return KEY_CLASS_METADATA_JSON
        if tail.startswith("snap-") and tail.endswith(".avro"):
            return KEY_CLASS_MANIFEST_LIST
        if tail.endswith(".avro"):
            return KEY_CLASS_MANIFEST
        return KEY_CLASS_OTHER

    if "/raw/" in key:
        return KEY_CLASS_RAW
    if "/data/" in key or tail.endswith(".parquet"):
        return KEY_CLASS_DATA
    return KEY_CLASS_OTHER


def cost_tier(service: str, operation: str) -> str:
    """Return the billing tier -- ``put``, ``get``, ``delete`` or ``glue``."""
    if service == "glue":
        return "glue"
    if operation in constants.DELETE_TIER_OPERATIONS:
        return "delete"
    if operation in constants.PUT_TIER_OPERATIONS:
        return "put"
    return "get"


def _extract_key(url: str, bucket: str) -> str:
    """Pull the object key out of a request URL, handling both addressing styles."""
    path = unquote(urlparse(url).path).lstrip("/")
    # Path-style addressing puts the bucket in front of the key.
    if path == bucket:
        return ""
    if path.startswith(f"{bucket}/"):
        return path[len(bucket) + 1 :]
    return path


def _header_int(headers: Any, name: str) -> int:
    """Best-effort Content-Length lookup across dict and HTTPHeaders shapes."""
    if not headers:
        return 0
    try:
        raw = headers.get(name) or headers.get(name.lower())
    except AttributeError:
        return 0
    if isinstance(raw, bytes | bytearray):
        raw = raw.decode("ascii", "ignore")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _body_size(body: Any) -> int:
    """Size of an outbound request body without consuming it.

    botocore does not set ``Content-Length`` on the request dict at
    ``before-call``: PutObject bodies arrive as a ``BytesIO`` and the length is
    only fixed later during signing, at which point large uploads have switched
    to ``aws-chunked`` transfer encoding and carry no ``Content-Length`` at all.
    Measuring the stream here -- and restoring its position -- is the one place
    the true payload size is reliably available.
    """
    if body is None:
        return 0
    if isinstance(body, bytes | bytearray):
        return len(body)
    if isinstance(body, str):
        return len(body.encode("utf-8"))

    seek: Any = getattr(body, "seek", None)
    tell: Any = getattr(body, "tell", None)
    if not (callable(seek) and callable(tell)):
        return 0
    try:
        original = int(tell())
        seek(0, 2)  # SEEK_END
        size = int(tell())
        seek(original)
        return max(0, size - original)
    except (OSError, ValueError, TypeError):
        return 0


@dataclass
class CallRecord:
    """One logical AWS API operation."""

    phase: str
    service: str
    operation: str
    key: str
    key_class: str
    tier: str
    request_bytes: int = 0
    response_bytes: int = 0
    duration_ms: float = 0.0
    status: int = 0


@dataclass
class PhaseStats:
    """Aggregates for a single phase, assembled by :meth:`Meter.summarize`."""

    phase: str
    wall_seconds: float = 0.0
    calls: int = 0
    attempts: int = 0
    request_bytes: int = 0
    response_bytes: int = 0
    by_tier: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    by_operation: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    by_key_class: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    # key_class -> {operation -> count}, the table that actually explains cost.
    by_key_class_operation: dict[str, dict[str, int]] = field(default_factory=dict)
    latencies_ms: list[float] = field(default_factory=list)

    @property
    def cost_usd(self) -> float:
        return (
            self.by_tier["put"] * constants.COST_PER_PUT_REQUEST
            + self.by_tier["get"] * constants.COST_PER_GET_REQUEST
            + self.by_tier["delete"] * constants.COST_PER_DELETE_REQUEST
            + self.by_tier["glue"] * constants.COST_PER_GLUE_REQUEST
        )

    def percentile(self, pct: float) -> float:
        """Nearest-rank percentile of call latency, in milliseconds."""
        if not self.latencies_ms:
            return 0.0
        ordered = sorted(self.latencies_ms)
        idx = max(0, min(len(ordered) - 1, int(round(pct / 100.0 * len(ordered))) - 1))
        return ordered[idx]


class Meter:
    """Thread-safe collector for AWS calls, attributed to the active phase.

    PyIceberg fans manifest and data-file work out across a thread pool, so the
    counters take a lock and the active phase is module-level rather than a
    ``contextvar`` (context does not propagate into ``ThreadPoolExecutor``
    workers). Phases run sequentially, so a plain global is correct here.
    """

    def __init__(self, bucket: str = constants.S3_BUCKET) -> None:
        self.bucket = bucket
        self.records: list[CallRecord] = []
        self.attempts: dict[str, int] = defaultdict(int)
        self.phase_wall: dict[str, float] = defaultdict(float)
        self._phase = _UNSET_PHASE
        self._lock = threading.Lock()
        self._installed = False

    # -- phase control --------------------------------------------------------

    @property
    def current_phase(self) -> str:
        return self._phase

    @contextmanager
    def phase(self, name: str) -> Generator[None, None, None]:
        """Attribute every AWS call made inside the block to ``name``."""
        previous = self._phase
        self._phase = name
        started = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - started
            with self._lock:
                self.phase_wall[name] += elapsed
            self._phase = previous

    # -- botocore handlers ----------------------------------------------------

    def _on_before_call(self, params: Any = None, context: Any = None, **_: Any) -> None:
        """Stash timing, phase, URL and request size while the request dict is in hand.

        The response object botocore hands to ``after-call`` carries neither the
        URL nor the outbound body size, so both are captured here.
        """
        if context is None:
            return
        context["_iceberg_meter_start"] = time.perf_counter()
        context["_iceberg_meter_phase"] = self._phase

        if not isinstance(params, dict):
            return
        context["_iceberg_meter_url"] = params.get("url", "")

        headers = params.get("headers")
        request_bytes = _header_int(headers, "Content-Length") or _header_int(
            headers, "X-Amz-Decoded-Content-Length"
        )
        if not request_bytes:
            request_bytes = _body_size(params.get("body"))
        context["_iceberg_meter_request_bytes"] = request_bytes

    def _on_before_send(self, **_: Any) -> None:
        """Count HTTP attempts. ``attempts`` above ``calls`` means botocore retried."""
        phase = self._phase
        with self._lock:
            self.attempts[phase] += 1

    def _on_after_call(
        self,
        http_response: Any = None,
        model: Any = None,
        context: Any = None,
        **_: Any,
    ) -> None:
        if model is None:
            return

        ctx = context if isinstance(context, dict) else {}
        started = ctx.get("_iceberg_meter_start")
        duration_ms = (time.perf_counter() - started) * 1000 if started else 0.0
        phase = ctx.get("_iceberg_meter_phase") or self._phase

        service = getattr(getattr(model, "service_model", None), "endpoint_prefix", "") or ""
        operation = getattr(model, "name", "") or ""

        key = _extract_key(ctx.get("_iceberg_meter_url", ""), self.bucket)
        request_bytes = ctx.get("_iceberg_meter_request_bytes", 0)

        response_bytes = 0
        status = 0
        if http_response is not None:
            status = getattr(http_response, "status_code", 0) or 0
            response_bytes = _header_int(getattr(http_response, "headers", None), "Content-Length")

        record = CallRecord(
            phase=phase,
            service=service,
            operation=operation,
            key=key,
            key_class=classify_key(key) if service == "s3" else KEY_CLASS_OTHER,
            tier=cost_tier(service, operation),
            request_bytes=request_bytes,
            response_bytes=response_bytes,
            duration_ms=duration_ms,
            status=status,
        )
        with self._lock:
            self.records.append(record)

    # -- installation ---------------------------------------------------------

    def install(self) -> None:
        """Patch botocore so all current and future sessions report to this meter.

        Idempotent. Must run before any boto3/aiobotocore client is constructed,
        since sessions built earlier will not carry the handlers.
        """
        if self._installed:
            return
        self._installed = True

        original_init = getattr(
            botocore.session.Session,
            "_iceberg_meter_original_init",
            botocore.session.Session.__init__,
        )

        meter = self

        def patched_init(session_self: Any, *args: Any, **kwargs: Any) -> None:
            original_init(session_self, *args, **kwargs)
            meter._register_on(session_self)

        botocore.session.Session._iceberg_meter_original_init = original_init  # type: ignore[attr-defined]
        botocore.session.Session.__init__ = patched_init  # type: ignore[method-assign]

    def _register_on(self, session: Any) -> None:
        for service in ("s3", "glue"):
            session.register(
                f"before-call.{service}.*",
                self._on_before_call,
                unique_id=f"iceberg-meter-before-{service}",
            )
            session.register(
                f"after-call.{service}.*",
                self._on_after_call,
                unique_id=f"iceberg-meter-after-{service}",
            )
            session.register(
                f"before-send.{service}.*",
                self._on_before_send,
                unique_id=f"iceberg-meter-send-{service}",
            )

    # -- reporting ------------------------------------------------------------

    def summarize(self) -> dict[str, PhaseStats]:
        """Fold the raw call log into per-phase aggregates."""
        with self._lock:
            records = list(self.records)
            attempts = dict(self.attempts)
            wall = dict(self.phase_wall)

        stats: dict[str, PhaseStats] = {}
        for record in records:
            entry = stats.setdefault(record.phase, PhaseStats(phase=record.phase))
            entry.calls += 1
            entry.request_bytes += record.request_bytes
            entry.response_bytes += record.response_bytes
            entry.by_tier[record.tier] += 1
            entry.by_operation[f"{record.service}:{record.operation}"] += 1
            entry.by_key_class[record.key_class] += 1
            per_class = entry.by_key_class_operation.setdefault(record.key_class, defaultdict(int))
            per_class[record.operation] += 1
            entry.latencies_ms.append(record.duration_ms)

        for phase, seconds in wall.items():
            stats.setdefault(phase, PhaseStats(phase=phase)).wall_seconds = seconds
        for phase, count in attempts.items():
            stats.setdefault(phase, PhaseStats(phase=phase)).attempts = count

        return stats

    def reset(self) -> None:
        with self._lock:
            self.records.clear()
            self.attempts.clear()
            self.phase_wall.clear()


# Module-level singleton -- the experiment runner installs this once at startup.
METER = Meter()

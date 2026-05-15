"""
End-to-end smoke test for the telemetry demo FastAPI app and LGTM compose stack.

How to run (from ``telemetry/app``)::

    uv sync
    uv run python tests/smoke_tests/smoke.py

Prerequisites: Docker with Compose v2, ``uv`` on PATH, hosts ``127.0.0.1:8082`` and
``127.0.0.1:3000`` available.

What it does, in order:

1. **Sync Python env** (unless ``--skip-uv-sync``): runs ``uv sync`` in the app
   directory; checks that the lockfile resolves and the venv is usable (same as
   the runbook / PR “install deps” step).

2. **Start stack** (unless ``--skip-compose``): runs ``docker compose up -d [--build]``
   from ``telemetry/app``, same as ``docs/runbooks/demo-app-setup.md``. Brings up
   ``app`` (FastAPI on 8082) and ``otel-lgtm`` (Grafana on 3000, OTLP on 4318).

3. **Wait for app**: polls ``GET /hello`` until HTTP 200 or ``--compose-timeout``.
   Checks the service is actually accepting traffic, not only that containers started.

4. **Check ``GET /hello``**: status 200 and JSON body ``{"message": "hello"}``.

5. **Check ``GET /error``**: status 500 (intentional server error per runbook).

6. **Check ``GET /slow``**: status 200 and ``{"slept_ms": 1000}`` (default delay).

7. **Check ``GET /slow?ms=2000``**: status 200, ``{"slept_ms": 2000}``, and wall-clock
   elapsed ≥ 1.5s so the delay is not a no-op.

8. **Check Grafana** (unless ``--skip-grafana``): ``GET /api/health`` on port 3000
   with Basic auth ``admin`` / ``admin``; requires HTTP 200 and JSON
   ``{"database": "ok", ...}``. Confirms the LGTM bundle is responding like a manual
   browser open to localhost:3000.

9. **Teardown** (unless ``--no-teardown`` or ``--skip-compose``): ``docker compose down``.

Not covered here (still manual or future automation): exploring Tempo traces, Loki log
lines, or Prometheus metrics inside Grafana UI as described in
``docs/runbooks/demo-app-usage.md``.
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# telemetry/app (directory containing Dockerfile, docker-compose.yml, pyproject.toml)
APP_ROOT = Path(__file__).resolve().parents[2]

APP_BASE = "http://127.0.0.1:8082"
GRAFANA_BASE = "http://127.0.0.1:3000"
DEFAULT_COMPOSE_TIMEOUT_S = 180
DEFAULT_HTTP_TIMEOUT_S = 15
POLL_INTERVAL_S = 2


class SmokeError(Exception):
    """Unrecoverable smoke failure."""


def run_cmd(
    argv: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd or APP_ROOT,
        check=check,
        text=True,
        capture_output=True,
    )


def http_json(
    method: str,
    url: str,
    *,
    timeout_s: float,
    expected_status: int | None = None,
    basic_auth: tuple[str, str] | None = None,
) -> tuple[int, Any]:
    req = urllib.request.Request(url, method=method)
    if basic_auth:
        token = base64.b64encode(
            f"{basic_auth[0]}:{basic_auth[1]}".encode(),
        ).decode("ascii")
        req.add_header("Authorization", f"Basic {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode()
            status = resp.status
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        status = e.code
        if expected_status is not None and status != expected_status:
            raise SmokeError(
                f"{method} {url} -> {status} (expected {expected_status}): {body[:500]}",
            ) from e
        try:
            parsed: Any = json.loads(body) if body.strip() else None
        except json.JSONDecodeError:
            parsed = body
        return status, parsed
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise SmokeError(f"{method} {url} transport error: {e}") from e
    if expected_status is not None and status != expected_status:
        raise SmokeError(
            f"{method} {url} -> {status} (expected {expected_status}): {body[:500]}",
        )
    try:
        parsed = json.loads(body) if body.strip() else None
    except json.JSONDecodeError:
        parsed = body
    return status, parsed


def wait_for_app_ready(*, timeout_s: float, http_timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    last_err: str | None = None
    while time.monotonic() < deadline:
        try:
            status, _ = http_json("GET", f"{APP_BASE}/hello", timeout_s=http_timeout_s)
            if status == 200:
                return
            last_err = f"GET /hello returned {status}"
        except (urllib.error.URLError, SmokeError, TimeoutError, OSError) as e:
            last_err = str(e)
        time.sleep(POLL_INTERVAL_S)
    raise SmokeError(f"App not ready within {timeout_s}s: {last_err}")


def compose_up(*, build: bool) -> None:
    args = ["docker", "compose", "up", "-d"]
    if build:
        args.append("--build")
    proc = run_cmd(args, check=False)
    if proc.returncode != 0:
        raise SmokeError(
            f"docker compose up failed ({proc.returncode})\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
        )


def compose_down() -> None:
    proc = run_cmd(["docker", "compose", "down"], check=False)
    if proc.returncode != 0:
        print(
            f"warning: docker compose down failed ({proc.returncode})\n{proc.stderr}",
            file=sys.stderr,
        )


def sync_deps() -> None:
    proc = run_cmd(["uv", "sync"], check=False)
    if proc.returncode != 0:
        raise SmokeError(
            f"uv sync failed ({proc.returncode})\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
        )


def check_grafana_health(*, http_timeout_s: float) -> None:
    status, data = http_json(
        "GET",
        f"{GRAFANA_BASE}/api/health",
        timeout_s=http_timeout_s,
        expected_status=200,
        basic_auth=("admin", "admin"),
    )
    if status != 200:
        raise SmokeError(f"Grafana health: unexpected status {status}")
    if not isinstance(data, dict):
        raise SmokeError(f"Grafana health: expected JSON object, got {type(data)}")
    # Grafana returns {"database": "ok", ...}
    if data.get("database") != "ok":
        raise SmokeError(f"Grafana database not ok: {data}")


def check_endpoints(*, http_timeout_s: float) -> None:
    status, data = http_json(
        "GET",
        f"{APP_BASE}/hello",
        timeout_s=http_timeout_s,
        expected_status=200,
    )
    if not isinstance(data, dict) or data.get("message") != "hello":
        raise SmokeError(f"/hello: unexpected body {data!r}")

    status, _ = http_json(
        "GET",
        f"{APP_BASE}/error",
        timeout_s=http_timeout_s,
        expected_status=500,
    )
    if status != 500:
        raise SmokeError(f"/error: expected 500, got {status}")

    status, data = http_json(
        "GET",
        f"{APP_BASE}/slow",
        timeout_s=http_timeout_s,
        expected_status=200,
    )
    if not isinstance(data, dict) or data.get("slept_ms") != 1000:
        raise SmokeError(f"/slow: expected slept_ms 1000, got {data!r}")

    t0 = time.monotonic()
    status, data = http_json(
        "GET",
        f"{APP_BASE}/slow?ms=2000",
        timeout_s=http_timeout_s + 5,
        expected_status=200,
    )
    elapsed_ms = (time.monotonic() - t0) * 1000
    if not isinstance(data, dict) or data.get("slept_ms") != 2000:
        raise SmokeError(f"/slow?ms=2000: unexpected body {data!r}")
    if elapsed_ms < 1500:
        raise SmokeError(
            f"/slow?ms=2000: expected wall time >= 1500ms, got {elapsed_ms:.0f}ms",
        )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--skip-uv-sync",
        action="store_true",
        help="Do not run `uv sync` before compose.",
    )
    p.add_argument(
        "--skip-compose",
        action="store_true",
        help="Assume stack is already up; only run HTTP checks.",
    )
    p.add_argument(
        "--no-teardown",
        action="store_true",
        help="Leave containers running after successful checks.",
    )
    p.add_argument(
        "--no-build",
        action="store_true",
        help="Skip `docker compose up --build` (use plain up).",
    )
    p.add_argument(
        "--compose-timeout",
        type=float,
        default=DEFAULT_COMPOSE_TIMEOUT_S,
        help=f"Seconds to wait for app /hello (default: {DEFAULT_COMPOSE_TIMEOUT_S}).",
    )
    p.add_argument(
        "--http-timeout",
        type=float,
        default=DEFAULT_HTTP_TIMEOUT_S,
        help=f"Per-request timeout in seconds (default: {DEFAULT_HTTP_TIMEOUT_S}).",
    )
    p.add_argument(
        "--skip-grafana",
        action="store_true",
        help="Skip Grafana /api/health (admin:admin).",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    teardown = not args.no_teardown and not args.skip_compose

    try:
        if not args.skip_uv_sync:
            print("Running uv sync…")
            sync_deps()

        if not args.skip_compose:
            print("Starting docker compose…")
            compose_up(build=not args.no_build)
            print(f"Waiting for app (up to {args.compose_timeout}s)…")
            wait_for_app_ready(
                timeout_s=args.compose_timeout,
                http_timeout_s=args.http_timeout,
            )
        else:
            print("Skipping compose; checking existing stack…")
            wait_for_app_ready(
                timeout_s=args.compose_timeout,
                http_timeout_s=args.http_timeout,
            )

        print("Checking API endpoints…")
        check_endpoints(http_timeout_s=args.http_timeout)

        if not args.skip_grafana:
            print("Checking Grafana health…")
            check_grafana_health(http_timeout_s=args.http_timeout)

        print("Smoke checks passed.")
        return 0
    except SmokeError as e:
        print(f"SMOKE FAILED: {e}", file=sys.stderr)
        return 1
    finally:
        if teardown:
            print("Tearing down compose stack…")
            compose_down()


if __name__ == "__main__":
    raise SystemExit(main())

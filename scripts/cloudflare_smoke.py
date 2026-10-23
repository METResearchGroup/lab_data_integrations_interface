"""Smoke checks for the Cloudflare preview of the API and the UI.

Does not print secret values. A full /query that reaches S3 needs a real
Supabase access token, which this script does not have. Without one, /query
stops at the bearer check (or at the origin guard, if ORIGIN_SECRET is set).

Run from the repo root:

    python scripts/cloudflare_smoke.py \\
        --api-url https://ldi-api-preview.mind-technology-lab.workers.dev \\
        --ui-url https://ldi-ui-preview.mind-technology-lab.workers.dev
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request

USER_AGENT = "ldi-cloudflare-smoke/1.0"
TIMEOUT_SECONDS = 180


def request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
) -> tuple[int, dict[str, str], bytes]:
    merged = {"User-Agent": USER_AGENT}
    if headers:
        merged.update(headers)
    req = urllib.request.Request(url, data=body, headers=merged, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()


def detail(payload: bytes) -> str:
    try:
        body = json.loads(payload)
    except json.JSONDecodeError:
        return payload.decode("utf-8", errors="replace")[:200]
    if isinstance(body, dict) and isinstance(body.get("detail"), str):
        return body["detail"]
    return payload.decode("utf-8", errors="replace")[:200]


def note_failure(failures: list[str], message: str | None) -> None:
    if message is not None:
        failures.append(message)


def check_health(api: str, failures: list[str]) -> None:
    status, _, body = request(f"{api}/health")
    print(f"GET /health -> {status} {body[:80]!r}")
    if status != 200 or body != b'{"status":"ok"}':
        failures.append(f"/health returned {status}")


def missing_bearer_failure(status: int, query_detail: str) -> str | None:
    # HTTPBearer rejects a missing Authorization header with 401 before the
    # handler runs. The origin middleware returns 403 detail "Forbidden" when
    # ORIGIN_SECRET is set and X-Origin-Secret is absent.
    if status == 401 and query_detail == "Not authenticated":
        print("  origin guard is open; the bearer check rejected the call")
        return None
    if status == 403 and query_detail == "Forbidden":
        print("  origin guard rejected the call (ORIGIN_SECRET is set)")
        return None
    return f"/query without credentials returned {status} {query_detail!r}"


def check_missing_bearer(api: str, failures: list[str]) -> None:
    status, _, body = request(
        f"{api}/query",
        method="POST",
        headers={"Content-Type": "application/json"},
        body=json.dumps("smoke").encode(),
    )
    query_detail = detail(body)
    print(f"POST /query without credentials -> {status} detail={query_detail!r}")
    note_failure(failures, missing_bearer_failure(status, query_detail))


def bogus_bearer_failure(status: int, token_detail: str) -> str | None:
    if status == 401 and token_detail == "Invalid access token":
        print("  Supabase JWT check ran; S3 is not reached without a valid token")
        return None
    if status == 403 and token_detail == "Forbidden":
        print("  origin guard rejected the call before JWT verification")
        return None
    return f"/query with a bogus bearer returned {status} {token_detail!r}"


def check_bogus_bearer(api: str, failures: list[str]) -> None:
    status, _, body = request(
        f"{api}/query",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer not-a-jwt",
        },
        body=json.dumps("smoke").encode(),
    )
    token_detail = detail(body)
    print(f"POST /query with a bogus bearer -> {status} detail={token_detail!r}")
    note_failure(failures, bogus_bearer_failure(status, token_detail))


def check_cors(api: str, ui: str, failures: list[str]) -> None:
    status, headers, _ = request(
        f"{api}/query",
        method="OPTIONS",
        headers={
            "Origin": ui,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    allow_origin = headers.get("Access-Control-Allow-Origin") or headers.get(
        "access-control-allow-origin"
    )
    print(f"OPTIONS /query Origin={ui} -> {status} allow-origin={allow_origin}")
    if allow_origin != ui:
        failures.append(f"CORS preflight did not echo the UI origin (status {status})")


def check_ui(ui: str, failures: list[str]) -> None:
    status, _, body = request(ui)
    text = body.decode("utf-8", errors="replace")
    print(f"GET UI -> {status} bytes={len(body)}")
    if status != 200:
        failures.append(f"UI returned {status}")
        return
    if "Lab Data Integrations" not in text and "Sign in" not in text:
        failures.append("UI body did not contain the app title or the sign-in page")


def report(failures: list[str]) -> None:
    if not failures:
        print("\nOK")
        return
    print("\nFAILED")
    for item in failures:
        print(f"  - {item}")
    raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--ui-url", required=True)
    args = parser.parse_args()
    api = args.api_url.rstrip("/")
    ui = args.ui_url.rstrip("/")
    failures: list[str] = []
    check_health(api, failures)
    check_missing_bearer(api, failures)
    check_bogus_bearer(api, failures)
    check_cors(api, ui, failures)
    check_ui(ui, failures)
    report(failures)


if __name__ == "__main__":
    main()

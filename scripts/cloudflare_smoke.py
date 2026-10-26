"""Smoke checks for the Cloudflare API and UI hosts.

Does not print secret values. Does not follow the Access redirect, so the
Location URL is not printed. Does not check Jetstream or the backfill worker.

Each step below fails the run unless the expected result is observed.
A skipped step is printed and does not fail the run.

1. GET {api}/health. Expect 200 and body {"status":"ok"}.
2. POST {api}/query with body "smoke" and no Authorization header.
   Expect 401 and detail "Not authenticated".
3. POST {api}/query with body "smoke" and Authorization "Bearer not-a-jwt".
   Expect 401 and detail "Invalid access token".
4. OPTIONS {api}/query with Origin set to {ui}. Expect
   Access-Control-Allow-Origin equal to {ui}.
5. GET {ui} with no Access token. Do not follow redirects. Expect status
   301, 302, 303, 307, or 308, and a Location host containing
   cloudflareaccess.com.
6. GET {ui}/ and GET {ui}/login with the Access service token. The token
   is CF_ACCESS_CLIENT_ID and CF_ACCESS_CLIENT_SECRET, or Secrets Manager
   lab-data-integrations-access-smoke in us-east-2. Expect 200, the body
   contains "Sign in" and type="password", and the body does not contain
   "Internal Server Error". If the token is missing, this step fails.
7. Signed-in POST {api}/query. Skipped, and not a failure, when
   SUPABASE_TEST_EMAIL or SUPABASE_TEST_PASSWORD is unset. When both are
   set, read NEXT_PUBLIC_SUPABASE_URL and
   NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY from Secrets Manager
   lab-data-integrations-supabase-public, sign in with the password grant,
   and POST {api}/query with that access token, Origin {ui}, and body
   "smoke". Expect 202.

Run from the repo root:

    python scripts/cloudflare_smoke.py \\
        --api-url https://ldi-api-preview.mind-technology-lab.workers.dev \\
        --ui-url https://ldi-ui-preview.mind-technology-lab.workers.dev
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "ldi-cloudflare-smoke/1.0"
TIMEOUT_SECONDS = 180
ACCESS_HOST_SUFFIX = "cloudflareaccess.com"
ACCESS_SMOKE_SECRET_ID = "lab-data-integrations-access-smoke"
SUPABASE_PUBLIC_SECRET_ID = "lab-data-integrations-supabase-public"


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
    # handler runs.
    if status == 401 and query_detail == "Not authenticated":
        print("  the bearer check rejected the call")
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


def no_redirect_opener() -> urllib.request.OpenerDirector:
    class StopRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            del req, fp, code, msg, headers, newurl
            return None

    return urllib.request.build_opener(StopRedirect)


def access_headers() -> dict[str, str]:
    client_id = os.environ.get("CF_ACCESS_CLIENT_ID", "")
    client_secret = os.environ.get("CF_ACCESS_CLIENT_SECRET", "")
    if client_id and client_secret:
        return service_headers(client_id, client_secret)
    loaded = secret_json(ACCESS_SMOKE_SECRET_ID)
    if loaded is None:
        return {}
    client_id = loaded.get("CF_ACCESS_CLIENT_ID")
    client_secret = loaded.get("CF_ACCESS_CLIENT_SECRET")
    if not isinstance(client_id, str) or not isinstance(client_secret, str):
        return {}
    if not client_id or not client_secret:
        return {}
    return service_headers(client_id, client_secret)


def service_headers(client_id: str, client_secret: str) -> dict[str, str]:
    return {
        "CF-Access-Client-Id": client_id,
        "CF-Access-Client-Secret": client_secret,
    }


def secret_json(secret_id: str) -> dict[str, object] | None:
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        return None
    client = boto3.client("secretsmanager", region_name="us-east-2")
    try:
        response = client.get_secret_value(SecretId=secret_id)
    except ClientError:
        return None
    try:
        data = json.loads(response.get("SecretString") or "")
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def check_access_wall(ui: str, failures: list[str]) -> None:
    opener = no_redirect_opener()
    req = urllib.request.Request(ui, headers={"User-Agent": USER_AGENT}, method="GET")
    try:
        with opener.open(req, timeout=TIMEOUT_SECONDS) as response:
            status = response.status
            location = response.headers.get("Location")
    except urllib.error.HTTPError as error:
        status = error.code
        location = error.headers.get("Location")
    host = ""
    if location:
        host = urllib.parse.urlparse(location).hostname or ""
    print(f"GET UI without Access token -> {status} location_host={host}")
    if status not in (301, 302, 303, 307, 308) or ACCESS_HOST_SUFFIX not in host:
        failures.append(f"UI without an Access token did not redirect to Access ({status})")


def check_authenticated_page(
    url: str,
    label: str,
    headers: dict[str, str],
    failures: list[str],
) -> None:
    started = time.perf_counter()
    status, _, body = request(url, headers=headers)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    text = body.decode("utf-8", errors="replace")
    print(f"GET {label} with Access token -> {status} bytes={len(body)} ms={elapsed_ms}")
    if status != 200:
        failures.append(f"{label} behind Access returned {status}")
        return
    if "Internal Server Error" in text:
        failures.append(f"{label} behind Access rendered Internal Server Error")
        return
    if "Sign in" not in text or 'type="password"' not in text:
        failures.append(f"{label} behind Access did not render the Supabase sign-in form")


def check_authenticated_ui(ui: str, failures: list[str]) -> None:
    headers = access_headers()
    if not headers:
        failures.append(
            "Authenticated UI check did not run. Set CF_ACCESS_CLIENT_ID and "
            "CF_ACCESS_CLIENT_SECRET, or store them in Secrets Manager "
            + ACCESS_SMOKE_SECRET_ID
            + "."
        )
        return
    check_authenticated_page(ui + "/", "UI /", headers, failures)
    check_authenticated_page(ui + "/login", "UI /login", headers, failures)


def check_signed_in_query(api: str, ui: str, failures: list[str]) -> None:
    email = os.environ.get("SUPABASE_TEST_EMAIL", "")
    password = os.environ.get("SUPABASE_TEST_PASSWORD", "")
    if not email or not password:
        print(
            "SKIP signed-in /query. Set SUPABASE_TEST_EMAIL and "
            "SUPABASE_TEST_PASSWORD for a Supabase user. No test user is stored."
        )
        return
    public = secret_json(SUPABASE_PUBLIC_SECRET_ID)
    if public is None:
        failures.append("Could not read the Supabase public settings for a signed-in /query.")
        return
    url = public.get("NEXT_PUBLIC_SUPABASE_URL")
    key = public.get("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
    if not isinstance(url, str) or not isinstance(key, str) or not url or not key:
        failures.append("Supabase public settings are missing a field.")
        return
    status, _, body = request(
        url.rstrip("/") + "/auth/v1/token?grant_type=password",
        method="POST",
        headers={"apikey": key, "Content-Type": "application/json"},
        body=json.dumps({"email": email, "password": password}).encode(),
    )
    if status != 200:
        failures.append(f"Supabase password sign-in returned {status}")
        return
    try:
        token = json.loads(body).get("access_token")
    except json.JSONDecodeError:
        token = None
    if not isinstance(token, str) or not token:
        failures.append("Supabase password sign-in did not return an access token.")
        return
    query_status, _, query_body = request(
        f"{api}/query",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token,
            "Origin": ui,
        },
        body=json.dumps("smoke").encode(),
    )
    print(f"POST /query with a Supabase session -> {query_status}")
    if query_status != 202:
        failures.append(f"signed-in /query returned {query_status} {detail(query_body)!r}")


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
    check_access_wall(ui, failures)
    check_authenticated_ui(ui, failures)
    check_signed_in_query(api, ui, failures)
    report(failures)


if __name__ == "__main__":
    main()

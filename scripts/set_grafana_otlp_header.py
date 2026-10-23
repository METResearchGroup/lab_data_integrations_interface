"""Copy the Grafana Cloud OTLP header onto the preview Workers.

Reads OTEL_EXPORTER_OTLP_HEADERS from Secrets Manager
lab-data-integrations-interface-grafana-cloud-oltp-header in us-east-2 and
stores that value as the Wrangler secret of the same name on
ldi-api-preview, ldi-jetstream-preview, and ldi-backfill-preview. Does not
print the value. Does not change the Secrets Manager secret.

Also creates or updates two Workers observability destinations,
ldi-preview-grafana-logs and ldi-preview-grafana-traces, using the same
credential. The destination Authorization header uses a real space. The
Worker secret keeps the %20 encoding the Python exporter requires.

The container reads the secret only when it starts. Deploy the Worker with
`--containers-rollout none` so the new vars are forwarded, then restart the
API and Jetstream containers. See
docs/runbooks/HOW_TO_DEPLOY_TO_CLOUDFLARE.md.

    python scripts/set_grafana_otlp_header.py

Requires CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, and AWS credentials
for us-east-2.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SECRET_ID = "lab-data-integrations-interface-grafana-cloud-oltp-header"
SECRET_REGION = "us-east-2"
FIELD = "OTEL_EXPORTER_OTLP_HEADERS"
ENCODED_PREFIX = "Authorization=Basic%20"
ROOT = Path(__file__).resolve().parent.parent

# Same gateway as backend/telemetry/constants.py. Destinations need the signal path.
OTLP_BASE = "https://otlp-gateway-prod-us-east-3.grafana.net/otlp"
LOGS_DESTINATION = "ldi-preview-grafana-logs"
TRACES_DESTINATION = "ldi-preview-grafana-traces"
DESTINATIONS = (
    (LOGS_DESTINATION, "opentelemetry-logs", f"{OTLP_BASE}/v1/logs"),
    (TRACES_DESTINATION, "opentelemetry-traces", f"{OTLP_BASE}/v1/traces"),
)
WORKERS = (
    ("ldi-api-preview", ROOT / "cloudflare" / "backend"),
    ("ldi-jetstream-preview", ROOT / "cloudflare" / "jetstream"),
    ("ldi-backfill-preview", ROOT / "cloudflare" / "backfill"),
)
OBSERVABILITY_WORKERS = (
    "ldi-api-preview",
    "ldi-jetstream-preview",
    "ldi-backfill-preview",
    "ldi-ui-preview",
)


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def scrub(text: str, secret: str) -> str:
    """Drop lines that might repeat the credential."""

    kept: list[str] = []
    for line in text.splitlines():
        if secret and secret in line:
            continue
        lowered = line.lower()
        if "authorization" in lowered or "basic%20" in lowered or "basic " in lowered:
            continue
        kept.append(line)
    return "\n".join(kept)


def otlp_header() -> str:
    import boto3
    from botocore.exceptions import ClientError

    client = boto3.client("secretsmanager", region_name=SECRET_REGION)
    try:
        response = client.get_secret_value(SecretId=SECRET_ID)
    except ClientError as error:
        code = error.response.get("Error", {}).get("Code", "unknown")
        fail(f"Could not read Secrets Manager secret {SECRET_ID} ({code}).")
    try:
        data = json.loads(response.get("SecretString") or "")
    except json.JSONDecodeError:
        fail(f"Secrets Manager secret {SECRET_ID} is not JSON.")
    if not isinstance(data, dict):
        fail(f"Secrets Manager secret {SECRET_ID} is not an object.")
    header = data.get(FIELD)
    if not isinstance(header, str) or not header:
        fail(f"Secrets Manager secret {SECRET_ID} is missing {FIELD}.")
    if not header.startswith(ENCODED_PREFIX):
        fail(
            f"{FIELD} must start with Authorization=Basic%20. "
            "The value was not printed."
        )
    if " " in header:
        fail(f"{FIELD} contains a raw space. The Python exporter needs %20.")
    return header


def authorization_value(header: str) -> str:
    """Turn the OTEL env value into an HTTP Authorization header value."""

    encoded = header.split("=", 1)[1]
    decoded = urllib.parse.unquote(encoded)
    if not decoded.startswith("Basic ") or decoded.count(" ") != 1:
        fail("The header did not decode to a Basic authorization value.")
    return decoded


def put_worker_secret(worker: str, directory: Path, header: str) -> None:
    result = subprocess.run(
        [
            "npx",
            "wrangler",
            "secret",
            "put",
            FIELD,
            "--name",
            worker,
        ],
        input=header,
        text=True,
        cwd=directory,
        capture_output=True,
    )
    for stream in (result.stdout, result.stderr):
        cleaned = scrub(stream, header)
        if cleaned:
            print(cleaned)
    if result.returncode != 0:
        fail(f"wrangler secret put {FIELD} failed for {worker}. The value was not printed.")
    print(f"Set {FIELD} on {worker} from {SECRET_ID}.")


def cloudflare_json(method: str, path: str, body: dict | None, secret: str) -> dict:
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if not account or not token:
        fail("CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN must be set.")
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}{path}"
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        detail = scrub(error.read().decode(errors="replace"), secret)[:400]
        fail(f"Cloudflare {method} {path} returned {error.code}. {detail}")
    if not payload.get("success", True):
        fail(f"Cloudflare {method} {path} was not successful.")
    result = payload.get("result")
    if not isinstance(result, (dict, list)):
        fail(f"Cloudflare {method} {path} returned an unexpected result.")
    return payload


def ensure_destinations(auth_value: str, secret: str) -> None:
    payload = cloudflare_json("GET", "/workers/observability/destinations", None, secret)
    existing = payload["result"]
    if not isinstance(existing, list):
        fail("Destination list was not a list.")
    by_name = {
        item.get("name"): item
        for item in existing
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    for name, dataset, url in DESTINATIONS:
        body = {
            "name": name,
            "enabled": True,
            "configuration": {
                "type": "logpush",
                "logpushDataset": dataset,
                "url": url,
                "headers": {"Authorization": auth_value},
            },
        }
        if name in by_name:
            cloudflare_json(
                "PATCH",
                f"/workers/observability/destinations/{name}",
                body,
                secret,
            )
            print(f"Updated destination {name} for {dataset}.")
        else:
            cloudflare_json("POST", "/workers/observability/destinations", body, secret)
            print(f"Created destination {name} for {dataset}.")


def observability_body() -> dict:
    return {
        "observability": {
            "enabled": True,
            "logs": {
                "enabled": True,
                "invocation_logs": True,
                "head_sampling_rate": 1,
                "persist": False,
                "destinations": [LOGS_DESTINATION],
            },
            "traces": {
                "enabled": True,
                "head_sampling_rate": 1,
                "persist": False,
                "destinations": [TRACES_DESTINATION],
            },
        }
    }


def point_workers_at_grafana(secret: str) -> None:
    """Attach the destinations and stop storing a second copy in Cloudflare."""

    for worker in OBSERVABILITY_WORKERS:
        cloudflare_json(
            "PATCH",
            f"/workers/scripts/{worker}/script-settings",
            observability_body(),
            secret,
        )
        print(f"Pointed {worker} logs and traces at Grafana with persist false.")


def main() -> None:
    header = otlp_header()
    for worker, directory in WORKERS:
        put_worker_secret(worker, directory, header)
    ensure_destinations(authorization_value(header), header)
    point_workers_at_grafana(header)


if __name__ == "__main__":
    main()

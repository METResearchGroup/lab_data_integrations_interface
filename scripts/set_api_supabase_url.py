"""Point the API Worker at the same Supabase host the UI uses.

Reads NEXT_PUBLIC_SUPABASE_URL from Secrets Manager
lab-data-integrations-supabase-public in us-east-2 and stores that value as
the Wrangler secret SUPABASE_URL on ldi-api-preview. Does not print the
value. Does not change the Secrets Manager secret.

The container reads SUPABASE_URL only when it starts. Redeploy the API
image, or wait for the instance to sleep, after this script.

    python scripts/set_api_supabase_url.py

Requires CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, and AWS credentials
for us-east-2.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

SECRET_ID = "lab-data-integrations-supabase-public"
SECRET_REGION = "us-east-2"
FIELD = "NEXT_PUBLIC_SUPABASE_URL"
WORKER_DIR = Path(__file__).resolve().parent.parent / "cloudflare" / "backend"


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def supabase_url() -> str:
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
    url = data.get(FIELD)
    if not isinstance(url, str) or not url:
        fail(f"Secrets Manager secret {SECRET_ID} is missing {FIELD}.")
    host = urlparse(url).hostname or ""
    if not host.endswith(".supabase.co"):
        fail(f"{FIELD} must be a supabase.co project host. The value was not printed.")
    return url


def main() -> None:
    url = supabase_url()
    result = subprocess.run(
        ["npx", "wrangler", "secret", "put", "SUPABASE_URL"],
        input=url,
        text=True,
        cwd=WORKER_DIR,
        capture_output=True,
    )
    # Wrangler prints status lines. Drop anything that repeats the URL.
    for stream in (result.stdout, result.stderr):
        for line in stream.splitlines():
            if url in line or "supabase.co" in line:
                continue
            print(line)
    if result.returncode != 0:
        fail("wrangler secret put SUPABASE_URL failed. The value was not printed.")
    print(f"Set SUPABASE_URL on ldi-api-preview from {SECRET_ID} field {FIELD}.")


if __name__ == "__main__":
    main()

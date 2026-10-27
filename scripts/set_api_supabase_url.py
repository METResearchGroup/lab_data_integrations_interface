"""Check the Supabase host the API reads from Secrets Manager.

Reads NEXT_PUBLIC_SUPABASE_URL from Secrets Manager
lab-data-integrations-supabase-public in us-east-2. Does not print the
value. Does not change the secret. Does not store it on the Worker.

The API process copies that field into SUPABASE_URL at startup when
SUPABASE_URL is absent. See lib/aws/secrets_env.py.

    python scripts/set_api_supabase_url.py

Requires AWS credentials for us-east-2.
"""

from __future__ import annotations

import json
import sys
from typing import NoReturn
from urllib.parse import urlparse

SECRET_ID = "lab-data-integrations-supabase-public"
SECRET_REGION = "us-east-2"
FIELD = "NEXT_PUBLIC_SUPABASE_URL"


def fail(message: str) -> NoReturn:
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
    supabase_url()
    print(
        f"Checked {SECRET_ID} field {FIELD}. "
        "The API process reads that field when SUPABASE_URL is absent."
    )


if __name__ == "__main__":
    main()

"""Copy the backfill trigger token from AWS Secrets Manager to Cloudflare."""

import json
import subprocess
import sys
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

SECRET_ID = "ldi-backfill-trigger-token"
FIELD = "BACKFILL_TRIGGER_TOKEN"
WORKER_DIR = Path(__file__).resolve().parents[1] / "cloudflare" / "backfill"


def main() -> int:
    try:
        secret = boto3.client("secretsmanager", region_name="us-east-2").get_secret_value(
            SecretId=SECRET_ID
        ).get("SecretString", "")
    except (BotoCoreError, ClientError):
        print("Could not read the backfill secret from AWS Secrets Manager.", file=sys.stderr)
        return 1

    try:
        data = json.loads(secret)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        token = data.get(FIELD)
    elif secret.startswith(f"{FIELD}="):
        token = secret[len(FIELD) + 1 :]
    else:
        token = None
    if not isinstance(token, str) or not token or any(c.isspace() for c in token):
        print(f"Secret must contain a nonempty {FIELD} without whitespace.", file=sys.stderr)
        return 1

    try:
        result = subprocess.run(
            ["npx", "--no-install", "wrangler", "secret", "put", FIELD],
            cwd=WORKER_DIR,
            input=token,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        print("Could not run Wrangler. Install the backfill Worker dependencies first.", file=sys.stderr)
        return 1
    if result.returncode:
        print("Wrangler failed to update the backfill Worker secret.", file=sys.stderr)
        return 1
    print("Updated the backfill Worker secret. No backfill was started.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

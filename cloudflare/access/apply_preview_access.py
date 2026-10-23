"""Put Cloudflare Access in front of the preview UI and API workers.dev URLs.

The browser calls the API host directly. workers.dev is a public suffix, so an
Access cookie from the UI host is not sent to the API host. A service token in
the UI bundle would be public. /health and /query are public paths on the API
application. Supabase still checks the bearer token on /query.

This does not enable Access. If the account has not turned Zero Trust on, the
script stops and names that gap. It does not print tokens or the account id.

    python cloudflare/access/apply_preview_access.py

Requires CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

UI_HOST = "ldi-ui-preview.mind-technology-lab.workers.dev"
API_HOST = "ldi-api-preview.mind-technology-lab.workers.dev"
POLICY_NAME = "LDI preview OTP allow"
SERVICE_TOKEN_NAME = "ldi-preview-smoke"
SERVICE_POLICY_NAME = "LDI preview smoke service auth"
ACCESS_SMOKE_SECRET_ID = "lab-data-integrations-access-smoke"
OTP_NAME = "One-time PIN login"
EMAIL_DOMAINS = (
    "northwestern.edu",
    "u.northwestern.edu",
    "kellogg.northwestern.edu",
)
ALLOW_EMAIL = "markptorres1@gmail.com"
PUBLIC_PATHS = ("/health", "/query")
API_ROOT = "https://api.cloudflare.com/client/v4/accounts"


class AccessApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(f"HTTP {status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message


def main() -> None:
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    if not token or not account_id:
        raise SystemExit("Set CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID.")
    try:
        apply_preview_access(token, account_id)
    except AccessApiError as error:
        if "access.api.error.not_enabled" in f"{error.code} {error.message}":
            raise SystemExit(not_enabled_message()) from None
        raise SystemExit(str(error)) from None


def not_enabled_message() -> str:
    return "\n".join(
        (
            "Access is not enabled on this account.",
            "The Access API returned access.api.error.not_enabled.",
            "Open https://dash.cloudflare.com/ and click Enable Access",
            "(Zero Trust has to be turned on before any application can be created).",
            "The token reached that API. This failure is not a missing permission.",
            "After Access is enabled, this script needs both of these token permissions:",
            "- Access: Apps and Policies Write",
            "- Access: Organizations, Identity Providers, and Groups Write",
            "A later 10000 authentication error means one of those is missing.",
            "Jetstream and the backfill worker are not in this config.",
        )
    )


def apply_preview_access(token: str, account_id: str) -> None:
    otp_id = ensure_otp(token, account_id)
    policy_id = ensure_allow_policy(token, account_id, otp_id)
    service_token_id = ensure_service_token(token, account_id)
    if service_token_id is None:
        ensure_application(token, account_id, ui_application(policy_id, otp_id))
    else:
        service_policy_id = ensure_service_policy(token, account_id, service_token_id)
        ensure_application(
            token,
            account_id,
            ui_application(policy_id, otp_id, service_token_policy_id=service_policy_id),
        )
        print(f"Service auth policy {SERVICE_POLICY_NAME} is on {UI_HOST}.")
    ensure_application(token, account_id, api_application(policy_id, otp_id))
    print(f"Access policy {POLICY_NAME} is on {UI_HOST} and {API_HOST}.")
    print(f"Public paths on the API: {', '.join(PUBLIC_PATHS)}.")


def ensure_otp(token: str, account_id: str) -> str:
    providers = list_results(token, account_id, "/access/identity_providers")
    existing = find_one(providers, "type", "onetimepin", "one-time PIN identity provider")
    if existing is not None:
        return str(existing["id"])
    created = write_json(
        token,
        account_id,
        "POST",
        "/access/identity_providers",
        {"name": OTP_NAME, "type": "onetimepin", "config": {}},
    )
    return str(created["id"])


def ensure_allow_policy(token: str, account_id: str, otp_id: str) -> str:
    body = allow_policy(otp_id)
    policies = list_results(token, account_id, "/access/policies")
    existing = find_one(policies, "name", POLICY_NAME, "Access policy")
    if existing is None:
        created = write_json(token, account_id, "POST", "/access/policies", body)
        return str(created["id"])
    policy_id = str(existing["id"])
    write_json(token, account_id, "PUT", f"/access/policies/{policy_id}", body)
    return policy_id


def ensure_application(token: str, account_id: str, body: dict[str, object]) -> None:
    name = str(body["name"])
    apps = list_results(token, account_id, "/access/apps")
    existing = find_one(apps, "name", name, "Access application")
    if existing is None:
        write_json(token, account_id, "POST", "/access/apps", body)
        return
    write_json(token, account_id, "PUT", f"/access/apps/{existing['id']}", body)


def allow_policy(otp_id: str) -> dict[str, object]:
    include: list[dict[str, dict[str, str]]] = [
        {"email_domain": {"domain": domain}} for domain in EMAIL_DOMAINS
    ]
    include.append({"email": {"email": ALLOW_EMAIL}})
    return {
        "name": POLICY_NAME,
        "decision": "allow",
        "include": include,
        "require": [{"login_method": {"id": otp_id}}],
    }


def ui_application(
    policy_id: str,
    otp_id: str,
    *,
    service_token_policy_id: str | None = None,
) -> dict[str, object]:
    body = application(
        name="ldi-ui-preview",
        host=UI_HOST,
        policy_id=policy_id,
        otp_id=otp_id,
        overrides=[],
    )
    if service_token_policy_id is not None:
        body["policies"] = [
            {"id": service_token_policy_id, "precedence": 1},
            {"id": policy_id, "precedence": 2},
        ]
    return body


def api_application(policy_id: str, otp_id: str) -> dict[str, object]:
    overrides = [{"behavior": "public", "path_pattern": path} for path in PUBLIC_PATHS]
    return application(
        name="ldi-api-preview",
        host=API_HOST,
        policy_id=policy_id,
        otp_id=otp_id,
        overrides=overrides,
    )


def application(
    *,
    name: str,
    host: str,
    policy_id: str,
    otp_id: str,
    overrides: list[dict[str, str]],
) -> dict[str, object]:
    destination: dict[str, object] = {"type": "public", "uri": host}
    if overrides:
        destination["overrides"] = overrides
    return {
        "name": name,
        "type": "self_hosted",
        "domain": host,
        "session_duration": "24h",
        "app_launcher_visible": False,
        "auto_redirect_to_identity": True,
        "allowed_idps": [otp_id],
        "destinations": [destination],
        "policies": [{"id": policy_id, "precedence": 1}],
    }


def ensure_service_token(token: str, account_id: str) -> str | None:
    tokens = list_results(token, account_id, "/access/service_tokens")
    existing = find_one(tokens, "name", SERVICE_TOKEN_NAME, "Access service token")
    if existing is not None:
        if not smoke_secret_present():
            raise SystemExit(
                "Access service token "
                + SERVICE_TOKEN_NAME
                + " already exists, and Secrets Manager "
                + ACCESS_SMOKE_SECRET_ID
                + " does not have both smoke fields. Delete that token in Zero Trust and run this again."
            )
        return str(existing["id"])
    try:
        created = write_json(
            token,
            account_id,
            "POST",
            "/access/service_tokens",
            {"name": SERVICE_TOKEN_NAME, "duration": "8760h"},
        )
    except AccessApiError as error:
        if error.status == 403:
            print(
                "Could not create Access service token "
                + SERVICE_TOKEN_NAME
                + ". The API token needs permission Access: Service Tokens Write. "
                + "OTP login stays in place."
            )
            return None
        raise
    client_id = created.get("client_id")
    client_secret = created.get("client_secret")
    token_id = created.get("id")
    if (
        not isinstance(client_id, str)
        or not isinstance(client_secret, str)
        or not isinstance(token_id, str)
        or not client_id
        or not client_secret
    ):
        raise SystemExit("Access did not return a service token id pair.")
    store_smoke_secret(client_id, client_secret)
    print(
        "Stored the smoke service token in Secrets Manager "
        + ACCESS_SMOKE_SECRET_ID
        + ". Values were not printed."
    )
    return token_id


def ensure_service_policy(token: str, account_id: str, service_token_id: str) -> str:
    body = {
        "name": SERVICE_POLICY_NAME,
        "decision": "non_identity",
        "include": [{"service_token": {"token_id": service_token_id}}],
    }
    policies = list_results(token, account_id, "/access/policies")
    existing = find_one(policies, "name", SERVICE_POLICY_NAME, "Access policy")
    if existing is None:
        created = write_json(token, account_id, "POST", "/access/policies", body)
        return str(created["id"])
    policy_id = str(existing["id"])
    write_json(token, account_id, "PUT", f"/access/policies/{policy_id}", body)
    return policy_id


def smoke_secret_present() -> bool:
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        return False
    client = boto3.client("secretsmanager", region_name="us-east-2")
    try:
        response = client.get_secret_value(SecretId=ACCESS_SMOKE_SECRET_ID)
    except ClientError:
        return False
    try:
        data = json.loads(response.get("SecretString") or "")
    except json.JSONDecodeError:
        return False
    if not isinstance(data, dict):
        return False
    client_id = data.get("CF_ACCESS_CLIENT_ID")
    client_secret = data.get("CF_ACCESS_CLIENT_SECRET")
    return (
        isinstance(client_id, str)
        and bool(client_id)
        and isinstance(client_secret, str)
        and bool(client_secret)
    )


def store_smoke_secret(client_id: str, client_secret: str) -> None:
    import boto3
    from botocore.exceptions import ClientError

    payload = json.dumps(
        {
            "CF_ACCESS_CLIENT_ID": client_id,
            "CF_ACCESS_CLIENT_SECRET": client_secret,
        }
    )
    client = boto3.client("secretsmanager", region_name="us-east-2")
    try:
        client.create_secret(Name=ACCESS_SMOKE_SECRET_ID, SecretString=payload)
    except ClientError as error:
        code = error.response.get("Error", {}).get("Code", "")
        if code != "ResourceExistsException":
            raise SystemExit(
                "Could not store the smoke service token (" + code + "). Values were not printed."
            ) from None
        client.put_secret_value(SecretId=ACCESS_SMOKE_SECRET_ID, SecretString=payload)


def find_one(
    items: list[dict[str, object]],
    key: str,
    value: str,
    label: str,
) -> dict[str, object] | None:
    matches = [item for item in items if item.get(key) == value]
    if len(matches) > 1:
        raise SystemExit(f"More than one {label} matches {value}.")
    if not matches:
        return None
    return matches[0]


def list_results(token: str, account_id: str, path: str) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    page = 1
    while page < 20:
        payload = request_json(token, account_id, "GET", f"{path}?page={page}&per_page=100", None)
        result = payload.get("result")
        batch = result if isinstance(result, list) else []
        items.extend(item for item in batch if isinstance(item, dict))
        if len(batch) < 100:
            return items
        page += 1
    raise SystemExit(f"Access list {path} did not end.")


def write_json(
    token: str,
    account_id: str,
    method: str,
    path: str,
    body: dict[str, object],
) -> dict[str, object]:
    payload = request_json(token, account_id, method, path, body)
    result = payload.get("result")
    if not isinstance(result, dict):
        raise AccessApiError(200, "missing_result", method + " " + path)
    return result


def request_json(
    token: str,
    account_id: str,
    method: str,
    path: str,
    body: dict[str, object] | None,
) -> dict[str, object]:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        API_ROOT + "/" + account_id + path,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode()
            status = response.status
    except urllib.error.HTTPError as error:
        err = access_error(error.code, error.read().decode())
        raise AccessApiError(err.status, err.code, method + " " + path + " " + err.message) from None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise AccessApiError(status, "not_json", method + " " + path) from None
    if not isinstance(payload, dict):
        raise AccessApiError(status, "not_object", method + " " + path)
    if payload.get("success") is False:
        raise access_error(status, raw)
    return payload


def access_error(status: int, raw: str) -> AccessApiError:
    code, message = parse_error(raw)
    return AccessApiError(status, code, message)


def parse_error(raw: str) -> tuple[str, str]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return "unreadable", "response was not JSON"
    errors = payload.get("errors") if isinstance(payload, dict) else None
    if not isinstance(errors, list) or not errors:
        return "unknown", "response had no error entry"
    first = errors[0]
    if not isinstance(first, dict):
        return "unknown", "response had no error entry"
    code = first.get("message") or first.get("code") or "unknown"
    text = first.get("message") or ""
    return str(code), str(text)


if __name__ == "__main__":
    main()

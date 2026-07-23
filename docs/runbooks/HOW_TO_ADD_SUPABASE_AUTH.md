# Supabase Auth Setup

## Overview

This runbook covers provisioning **Supabase Auth** so the frontend can obtain
a session token and the backend can verify it — the Supabase-side setup only.
It does not cover wiring auth into `ui/` or `backend/` routes.

Supabase issues JWTs. This project's Supabase instance uses the **new
asymmetric JWT signing keys** (ECC / **ES256**), not the legacy shared HS256
secret. That means the backend verifies tokens against Supabase's public
JWKS endpoint rather than a shared secret — there is no `SUPABASE_JWT_SECRET`
in this setup.

## Prerequisites

- A Supabase project at [supabase.com](https://supabase.com).
- Project Settings → API → JWT Settings shows key type **ECC (P-256)**. If
  it instead shows a plain JWT Secret string with no key type, the project is
  on the legacy HS256 scheme and the verification step below (JWKS) does not
  apply — use `pyjwt.decode(token, secret, algorithms=["HS256"])` instead.

## Keys to collect

From **Project Settings → API**:

| Key | Where used | Notes |
|---|---|---|
| Project URL (`https://<ref>.supabase.co`) | frontend + backend | Do **not** append `/rest/v1/` — that's the PostgREST path, not the base URL. |
| Publishable key (`sb_publishable_...`) | frontend only | Replaces the legacy "anon" key. Safe for the browser. |
| Secret key (`sb_secret_...`) | backend, only if making privileged Supabase API calls | Replaces the legacy "service_role" key. Bypasses RLS — never expose to the frontend. Not needed just to verify JWTs. |

## Dependencies

Frontend (`ui/`):

```bash
npm install @supabase/ssr @supabase/supabase-js
```

Backend (root, `uv`-managed):

```bash
uv add pyjwt
```

## Environment variables

Frontend — `ui/.env.local` (gitignored; template committed as
`ui/.env.local.example`):

```
NEXT_PUBLIC_SUPABASE_URL=https://<your-project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<your-publishable-key>
```

`NEXT_PUBLIC_` is required for Next.js to expose these client-side.

Backend — root `.env` (mirror in Railway's **Variables** tab, see
[backend-railway-deploy.md](backend-railway-deploy.md)):

```
SUPABASE_URL=https://<your-project-ref>.supabase.co
```

That's the only var needed on the backend — the JWKS URL
(`${SUPABASE_URL}/auth/v1/.well-known/jwks.json`) is derived from it, and
`PyJWKClient` fetches/caches the public key itself.

## Verifying the setup works

### 1. Get a real access token

1. Sign up to create a test user:

   ```bash
   curl -X POST 'https://<ref>.supabase.co/auth/v1/signup' \
     -H "apikey: <publishable-key>" \
     -H "Content-Type: application/json" \
     -d '{"email":"test@example.com","password":"testpassword123"}'
   ```

2. Log in to get the session (also used for any subsequent logins once the
   account already exists):

   ```bash
   curl -X POST 'https://<ref>.supabase.co/auth/v1/token?grant_type=password' \
     -H "apikey: <publishable-key>" \
     -H "Content-Type: application/json" \
     -d '{"email":"test@example.com","password":"testpassword123"}'
   ```

The login response's `access_token` field confirms the project URL and
publishable key are correct.

### 2. Confirm the token's algorithm

```python
import jwt
jwt.get_unverified_header(access_token)  # -> {"alg": "ES256", ...}
```

Should show `ES256`, matching the ECC (P-256) key type from Project Settings.

### 3. Verify the token via JWKS

```python
import jwt
from jwt import PyJWKClient

jwks_client = PyJWKClient("https://<ref>.supabase.co/auth/v1/.well-known/jwks.json")
signing_key = jwks_client.get_signing_key_from_jwt(access_token)

decoded = jwt.decode(access_token, signing_key.key, algorithms=["ES256"], audience="authenticated")
print(decoded)
```

`PyJWKClient` fetches the public key matching the token's `kid` from the
JWKS endpoint and verifies the ES256 signature. If this returns the payload
without raising, backend verification is working end-to-end.


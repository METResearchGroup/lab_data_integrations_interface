# How to Enable Microsoft Sign-In

## Overview

Adds **Continue with Microsoft** to `/login` and `/signup`. Northwestern users
sign in with their NetID through Microsoft; the first sign-in creates their
account. Email + password keeps working alongside it.

The button is hidden until `NEXT_PUBLIC_ENABLE_MICROSOFT_SIGN_IN=true`, so the
code can merge before any of this is set up.

`<project-ref>` is the subdomain of `NEXT_PUBLIC_SUPABASE_URL` in
`ui/.env.local`.

**Prerequisite:** the domain hook from
[HOW_TO_ENABLE_SELF_SERVE_SIGNUP.md](HOW_TO_ENABLE_SELF_SERVE_SIGNUP.md) step 1
is live. It runs on Microsoft sign-ups too and is still the real gate.

Northwestern tenant ID (covers `northwestern.edu`, `u.northwestern.edu` and
`kellogg.northwestern.edu`): `7d76d361-8277-4708-a477-64e8366cd1bc`. To
re-check:

```bash
curl -s https://login.microsoftonline.com/northwestern.edu/v2.0/.well-known/openid-configuration | jq -r .issuer
```

---

## 1. Register the app in Microsoft Entra

No Northwestern approval is needed to register. Use any Microsoft account; a
free Azure account comes with a directory.

`https://entra.microsoft.com` → **App registrations → New registration**:

- **Name**: `Kellogg Lab Data` (shown on Microsoft's consent screen).
- **Supported account types**: *Accounts in any organizational directory
  (Multitenant)*. Northwestern is a different tenant from yours.
- **Redirect URI**: Web →
  `https://<project-ref>.supabase.co/auth/v1/callback`

Then, in the app:

1. **Overview** → copy **Application (client) ID**.
2. **Certificates & secrets → New client secret** → copy the **Value** (not
   the ID). Note the expiry; sign-in breaks when it lapses.
3. **Token configuration → Add optional claim** → ID → tick `email` and
   `xms_edov` → add. Accept the prompt to add the Graph `email` permission.

`xms_edov` tells Supabase the email's domain is verified by the tenant.
Without it Supabase treats the address as unverified and won't link it to an
existing email + password account.

## 2. Configure Supabase

`https://supabase.com/dashboard/project/<project-ref>/auth/providers`
(sidebar: Authentication → Sign In / Providers) → **Azure**:

| Field | Value |
|---|---|
| Enabled | on |
| Application (client) ID | from step 1 |
| Secret Value | from step 1 |
| Azure Tenant URL | `https://login.microsoftonline.com/7d76d361-8277-4708-a477-64e8366cd1bc` |

The tenant URL limits sign-in to Northwestern accounts.

**Allow new users to sign up** must be on (it already is if self-serve signup
is enabled). Off means only existing users can sign in with Microsoft.

`https://supabase.com/dashboard/project/<project-ref>/auth/url-configuration`
→ **Redirect URLs** → add:

- `https://<vercel-production-domain>/auth/callback**`
- `http://localhost:3000/**` (likely already there)

If the callback isn't allowlisted, Supabase falls back to the Site URL and the
code is never exchanged, so the user lands back on `/login`.

## 3. Test Northwestern consent

Locally, set `NEXT_PUBLIC_ENABLE_MICROSOFT_SIGN_IN=true` in `ui/.env.local`,
run `npm run dev`, and click **Continue with Microsoft** with a NetID.

- **Permissions prompt → Accept → lands in the app**: done, go to step 4.
- **"Need admin approval"**: Northwestern only lets users consent to apps
  from verified publishers. Either:
  - Use **Request approval** on that screen, if shown, or ask the NU IT
    Service Desk for admin consent. Include the client ID and that it only
    asks to sign the user in and read their email address.
  - Verify as a publisher (needs a Microsoft AI Cloud Partner Program
    account tied to a domain you own), then retry.

  Until then, leave the flag off in production.

## 4. Turn on in production

Vercel → project → Settings → Environment Variables → add
`NEXT_PUBLIC_ENABLE_MICROSOFT_SIGN_IN` = `true` (Production) → redeploy. It's
inlined at build time, so a redeploy is required.

---

## Verify

1. `/login` → **Continue with Microsoft** → NetID → lands in the app.
2. Supabase → Authentication → Users → the user's provider shows `azure`.
3. A user who already had an email + password account → same user row, now
   with both `email` and `azure` identities.
4. A personal Microsoft account → rejected by Microsoft (wrong tenant), or by
   the hook → `/login` shows "Microsoft sign-in failed".

## Rollback

Set `NEXT_PUBLIC_ENABLE_MICROSOFT_SIGN_IN` to `false` and redeploy to hide the
button. To block it at the source too, turn **Azure** off in Supabase.
Users who only ever used Microsoft have no password. Authentication → Users →
the user → **Send password recovery**; the link lands on `/set-password`.

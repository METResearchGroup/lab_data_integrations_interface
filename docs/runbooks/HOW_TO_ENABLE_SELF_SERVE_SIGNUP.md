# How to Enable Self-Serve Signup

## Overview

Anyone with a `@kellogg.northwestern.edu` or `@u.northwestern.edu` email can create an account at
`/signup`. They verify the address with a 6-digit code emailed to them, then
land in the app. Invites ([HOW_TO_ADD_A_USER.md](HOW_TO_ADD_A_USER.md)) keep
working.

Needs a Supabase project owner/admin. All steps are dashboard config; no
deploy beyond merging the UI.

`<project-ref>` is the subdomain of `NEXT_PUBLIC_SUPABASE_URL` in
`ui/.env.local`.

**Do the steps in order.** Step 4 turns signups on; before that, the domain
hook (step 1) must be live or anyone can register.

---

## 1. Domain restriction hook

The form check in `ui/` is UX only. The publishable key ships in the browser,
so `POST /auth/v1/signup` can be called directly. This hook is the real gate.

`https://supabase.com/dashboard/project/<project-ref>/sql/new`
(sidebar: SQL Editor) — run:

```sql
create or replace function public.hook_restrict_signup_by_email_domain(event jsonb)
returns jsonb
language plpgsql
as $$
declare
  email text := lower(event->'user'->>'email');
begin
  if email is null or (email not like '%@kellogg.northwestern.edu'
                       and email not like '%@u.northwestern.edu'
                       and email <> 'person@gmail.com') then
    return jsonb_build_object(
      'error', jsonb_build_object(
        'http_code', 403,
        'message', 'Sign up requires a @kellogg.northwestern.edu or @u.northwestern.edu email.'
      )
    );
  end if;
  return '{}'::jsonb;
end;
$$;

grant execute on function public.hook_restrict_signup_by_email_domain to supabase_auth_admin;
revoke execute on function public.hook_restrict_signup_by_email_domain from authenticated, anon, public;
```

Then `https://supabase.com/dashboard/project/<project-ref>/auth/hooks`
(sidebar: Authentication → Hooks) → **Add hook → Before User Created** →
Postgres, schema `public`, function `hook_restrict_signup_by_email_domain` →
enable.

Domains must match `ALLOWED_EMAIL_DOMAINS` in `ui/src/lib/constants.ts`.

The hook also blocks console invites to other addresses. Replace
`person@gmail.com` with the address to let through; for more, use
`email not in ('a@gmail.com', 'b@gmail.com')`. Re-running the `create or
replace` keeps the hook attached.

It also gates Microsoft sign-in
([HOW_TO_ENABLE_MICROSOFT_SIGN_IN.md](HOW_TO_ENABLE_MICROSOFT_SIGN_IN.md)).

## 2. Custom SMTP

Supabase's built-in sender only delivers to the project's team members and is
heavily rate-limited. Without custom SMTP, signup codes never arrive.

Pick one.

### Option A — Resend (needs a domain you control)

Free tier: 3,000/month, 100/day.

1. Sign up at resend.com.
2. **Domains → Add Domain**, e.g. `mail.<your-domain>`. Can't be
   `northwestern.edu` — you need DNS access.
3. Add the SPF/DKIM/MX records Resend shows at your DNS provider →
   **Verify**.
4. **API Keys → Create API Key**, permission "Sending access". Copy it.
5. Fill in the SMTP settings below with:

   | Field | Value |
   |---|---|
   | Sender email | `noreply@mail.<your-domain>` |
   | Sender name | `Kellogg Lab Data` |
   | Host | `smtp.resend.com` |
   | Port | `465` |
   | Username | `resend` |
   | Password | API key from step 4 |

Resend's Supabase integration (Resend → Integrations) can fill these in for you.

### Option B — Gmail app password (no domain)

~500/day. Emails come from the Gmail address.

1. Turn on 2-Step Verification for the Google account.
2. `https://myaccount.google.com/apppasswords` → create one, copy the 16
   characters.
3. Fill in the SMTP settings below with:

   | Field | Value |
   |---|---|
   | Sender email | the Gmail address |
   | Sender name | `Kellogg Lab Data` |
   | Host | `smtp.gmail.com` |
   | Port | `465` |
   | Username | the Gmail address |
   | Password | app password |

### SMTP settings

`https://supabase.com/dashboard/project/<project-ref>/auth/smtp`
(sidebar: Authentication → Emails → SMTP Settings) → **Enable custom SMTP** →
fill in → save.

Then `https://supabase.com/dashboard/project/<project-ref>/auth/rate-limits`
(sidebar: Authentication → Rate Limits) → raise **emails per hour** (default
~30) if a whole class may sign up at once.

Check: invite yourself from Authentication → Users and confirm it arrives.

## 3. Confirm signup template: code, not link

Supabase generates both a link and a code for every confirmation; the template
decides which one the user sees. `/signup` expects a code.

University mail scanners pre-open links, which consumes the token before the
user clicks. A code can't be pre-opened.

`https://supabase.com/dashboard/project/<project-ref>/auth/templates`
(sidebar: Authentication → Emails) → **Confirm signup** tab. Replace the body:

```html
<h2>Confirm your email</h2>
<p>Your verification code is:</p>
<p style="font-size:24px;font-weight:bold;letter-spacing:4px">{{ .Token }}</p>
<p>This code expires in 1 hour.</p>
```

Remove `{{ .ConfirmationURL }}` entirely — the link and code share one token,
so a scanned link kills the code too.

Leave the **Invite user** template as is.

If the template editor is locked, finish step 2 first.

## 4. Turn on signups

`https://supabase.com/dashboard/project/<project-ref>/auth/providers`
(sidebar: Authentication → Sign In / Providers):

- **Allow new users to sign up** → on.
- **Email** provider → **Confirm email** → on.
- **Email OTP Length** → `6`. **Email OTP Expiration** → `3600`.
- Optional: minimum password length → 8+.

## 5. URL configuration

`https://supabase.com/dashboard/project/<project-ref>/auth/url-configuration`

- **Site URL**: Vercel production URL (likely already set).
- **Redirect URLs**: add `http://localhost:3000/**` for local dev.

---

## Verify

1. `/signup` with a non-Northwestern email → blocked by the form.
2. Bypass the form:
   ```bash
   curl -s -X POST "https://<project-ref>.supabase.co/auth/v1/signup" \
     -H "apikey: $NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY" \
     -H "Content-Type: application/json" \
     -d '{"email":"test@gmail.com","password":"some-password-123"}'
   ```
   → 403 with the hook's message. If it succeeds, step 1 isn't enabled —
   turn signups off until it is, and delete the user it created.
3. `/signup` with a real Kellogg or u.northwestern.edu address → code arrives → enter it → lands in
   the app.

## Rollback

Authentication → Sign In / Providers → **Allow new users to sign up** → off.
`/signup` then shows Supabase's "Signups not allowed" error; invites still
work.

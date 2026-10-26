# How to Add a User

## Overview

`@kellogg.northwestern.edu` and `@u.northwestern.edu` users can sign up themselves at `/signup` — see
[HOW_TO_ENABLE_SELF_SERVE_SIGNUP.md](HOW_TO_ENABLE_SELF_SERVE_SIGNUP.md).
Invites are for everyone else, or to add someone directly: invite from the
dashboard, user sets a password, signs in with email + password after that.

Auth provisioning: [HOW_TO_ADD_SUPABASE_AUTH.md](HOW_TO_ADD_SUPABASE_AUTH.md).

---

## One-time setup

All three required for invites.

`<project-ref>` below is the subdomain of `NEXT_PUBLIC_SUPABASE_URL` in
`ui/.env.local` — or just open the project in the dashboard and read it out of
the address bar.

### 1. URL configuration

`https://supabase.com/dashboard/project/<project-ref>/auth/url-configuration`
(sidebar: Authentication → URL Configuration)

Set **Site URL** to the deployed UI origin (the Cloudflare Worker URL in preview).

### 2. Invite email template

`https://supabase.com/dashboard/project/<project-ref>/auth/templates`
(sidebar: Authentication → Emails) → **Invite user** tab.

The field is the email's HTML body. Edit only the `href` on the invite link,
leave the rest:

```html
<a href="{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=invite">Accept the invite</a>
```

`{{ }}` vars are literal — Supabase fills them at send time.

Stock `{{ .ConfirmationURL }}` returns tokens in the URL fragment, which never
reaches the server. Sessions are cookie-based, so it can't work.

### 3. Public signups

Off unless self-serve signup is set up. Don't turn "Allow new users to sign
up" on without the domain hook from
[HOW_TO_ENABLE_SELF_SERVE_SIGNUP.md](HOW_TO_ENABLE_SELF_SERVE_SIGNUP.md) —
`POST /auth/v1/signup` is public and the publishable key ships in the client
bundle. Invites are unaffected either way.

---

## Adding a user

1. `https://supabase.com/dashboard/project/<project-ref>/auth/users`
   (sidebar: Authentication → Users)
2. **Add user → Invite user**, enter email, send.

## What they see

Email link → `/auth/confirm` (token traded for session) → `/set-password` → app.
Then `/login` with email + password from then on.

## Removing a user

Authentication → Users → row menu → **Delete user**. No soft delete.

# How to add a user

## Overview

Access is invite-only. There is no signup page, and self-serve signup is
disabled on the Supabase project. You invite someone from the dashboard. They
set a password, then they sign in with email and password after that.

Auth provisioning is in
[HOW_TO_ADD_SUPABASE_AUTH.md](HOW_TO_ADD_SUPABASE_AUTH.md).

---

## One-time setup

The steps below are required. Invite emails use **Site URL** as the link host.
Supabase defaults that field to `http://localhost:3000`. If you leave the
default, the invite opens on the recipient's machine instead of the live app.

`<project-ref>` below is the subdomain of `NEXT_PUBLIC_SUPABASE_URL` in
`ui/.env.local`. You can also open the project in the dashboard and read it
out of the address bar.

The repository cannot change the Supabase dashboard. You have to save Site
URL and Redirect URLs there.

### 1. URL configuration

`https://supabase.com/dashboard/project/<project-ref>/auth/url-configuration`
(sidebar: Authentication → URL Configuration)

Set **Site URL** to
`https://lab-data-integrations-interface.vercel.app`.

Do not add a trailing slash. The invite template appends `/auth/confirm`, and a
trailing slash would produce a double slash in the link.

Add `https://lab-data-integrations-interface.vercel.app/**` to
**Redirect URLs**.

You can keep `http://localhost:3000/**` in Redirect URLs for local testing. Do
not put localhost in Site URL.

### 2. Invite email template

`https://supabase.com/dashboard/project/<project-ref>/auth/templates`
(sidebar: Authentication → Emails) → **Invite user** tab.

The field is the email's HTML body. Edit only the `href` on the invite link,
leave the rest:

```html
<a href="{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=invite">Accept the invite</a>
```

`{{ }}` vars are literal. Supabase fills them at send time.

Stock `{{ .ConfirmationURL }}` returns tokens in the URL fragment, which never
reaches the server. Sessions are cookie-based, so it can't work.

### 3. Disable public signups

`https://supabase.com/dashboard/project/<project-ref>/auth/providers`
(sidebar: Authentication → Sign In / Providers) → Email → off "Allow new users
to sign up".

Required. `POST /auth/v1/signup` is public and the publishable key ships in the
client bundle. Anyone with the app URL can self-register until this is off.
Invites are unaffected.

### 4. Vercel Authentication

The production host is a `vercel.app` URL. Vercel Authentication is currently
on for every deployment that is not a custom domain. A person who is not on
the Vercel team hits a Vercel login wall before they ever reach
`/auth/confirm`, so they cannot accept the invite.

Before you invite someone who is not on the Vercel team, either turn Vercel
Authentication off for production, or put the app on a custom domain (custom
domains are excluded from that protection). A Vercel share link does not fix
invite emails.

---

## Adding a user

1. `https://supabase.com/dashboard/project/<project-ref>/auth/users`
   (sidebar: Authentication → Users)
2. **Add user → Invite user**, enter email, send.

## What they see

The email link opens
`https://lab-data-integrations-interface.vercel.app/auth/confirm`. The app
trades the token for a session, then sends them to `/set-password`. After they
save a password, they land on the query page, already signed in. Later visits
go through `/login` with email and password.

A missing or expired invite link lands on `/login` with an error that tells
them to ask for a new invite. They cannot set a password until they have a
working invite.

## Removing a user

Authentication → Users → row menu → **Delete user**. No soft delete.

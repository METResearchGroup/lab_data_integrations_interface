# How to Deploy the UI to Vercel

## Overview

This runbook covers how to deploy the repository’s current Next.js UI (the `ui/` folder) to Vercel.

Key points:
- The UI is a **Next.js App Router** app in `ui/`.
- The UI calls a separate backend API from the browser (client-side `fetch`), so the backend must be deployed separately and be reachable over HTTPS.
- The UI expects `NEXT_PUBLIC_API_URL` to be set on Vercel.

Relevant code:
- UI API base URL: `ui/src/lib/api.ts` (`NEXT_PUBLIC_API_URL`, fallback `http://localhost:8000`)
- Backend CORS: `backend/main.py` (`CORS_ORIGINS`, default `http://localhost:3000`)

---

## Prerequisites

- A deployed backend URL, e.g. `https://api.example.com`
- Access to the GitHub repo in Vercel
- Ability to set environment variables in both:
  - Vercel (for the UI)
  - Your backend hosting environment (for CORS)

---

## One-time setup (Vercel project)

1. In Vercel, create a new project and import the GitHub repo:
   - `METResearchGroup/lab_data_integrations_interface`

2. Configure the project to build from the UI folder:
   - **Root Directory**: `ui`
   - **Framework Preset**: Next.js

3. Set build commands (Vercel should auto-detect, but these are the expected values):
   - **Install Command**: `npm ci`
   - **Build Command**: `npm run build`
   - **Output Directory**: default (Next.js)

4. Ensure the runtime is compatible:
   - **Node.js**: 20.x (recommended)

---

## Required Vercel environment variables (UI)

In Vercel → Project → Settings → Environment Variables, set:

- `NEXT_PUBLIC_API_URL`:
  - **Production**: `https://<your-backend-host>`
  - **Preview** (recommended): `https://<your-backend-host>`

Notes:

- Do **not** include a trailing slash. The UI concatenates routes like `${BASE_URL}/posts/recent`.
- After changing env vars, you must trigger a redeploy (see “When the UI re-updates”).

---

## Backend CORS (required)

The backend must allow the Vercel UI origin.

Set the backend environment variable:

- `CORS_ORIGINS` = `https://<your-ui-domain>,http://localhost:3000`

Where:
- `https://<your-ui-domain>` is your Vercel production URL (or custom domain).
- Keep `http://localhost:3000` for local UI development.

Preview deployments:
- Vercel Preview deployments use unique `https://<random>.vercel.app` origins.
- With the current backend CORS configuration (explicit allowlist), previews will only work if you add the preview origin(s) to `CORS_ORIGINS`, or you adjust backend CORS policy to support preview origins.

---

## Deploy

Once the Vercel project is configured:

- Push/merge your changes to the tracked production branch (commonly `main`).
- Vercel will build and deploy the UI automatically.

---

## Verify deployment

1. Open the deployed UI URL.
2. Click “Run” for a query.
3. Confirm:
   - Results render in the table.
   - “Export CSV” triggers a download/open of a CSV file (the URL is returned by the backend as a presigned S3 URL).

If the UI shows an error:

- A CORS error typically means the backend `CORS_ORIGINS` is missing the Vercel UI origin.
- A network error or `404` typically means `NEXT_PUBLIC_API_URL` is unset or points to the wrong backend host.

---

## When the Vercel UI re-updates (what to expect)

Vercel will deploy new versions of the UI in these cases:

- **Production deployments**:
  - Triggered when commits land on the production branch configured in Vercel (commonly `main`).
  - Expect the updated UI to be live after the build completes (typically within a few minutes of the push/merge, depending on install/build time and Vercel queueing).

- **Preview deployments**:
  - Triggered for pull requests (each PR commit generates a new preview deployment).
  - Expect a new preview URL/build shortly after pushing commits to the PR branch.

- **Environment variable changes**:
  - Changing `NEXT_PUBLIC_API_URL` in Vercel does **not** affect already-built deployments.
  - You must create a **new deployment** (push a commit or manually redeploy the latest deployment) for env var changes to take effect.

Manual redeploy:
- Vercel → Project → Deployments → select the desired deployment → “Redeploy”.

---

## Common pitfalls

- **Using an HTTP backend in production**: browsers will block `http://...` API calls from an `https://...` UI (mixed content). Use an HTTPS backend URL for `NEXT_PUBLIC_API_URL`.
- **CORS not updated after custom domain changes**: if the UI domain changes, you must update `CORS_ORIGINS` to include the new origin.

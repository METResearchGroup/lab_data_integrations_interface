# How to Enable DDoS Protection

## Overview

Puts CloudFront and AWS WAF in front of the Railway backend:

```
client → CloudFront (+ WAF) → Railway
```

| | |
|---|---|
| Terraform | `terraform/backend_edge/main.tf` |
| Origin guard | `backend/origin.py` |
| WAF rules | `AWSManagedRulesAntiDDoSRuleSet` (block only), per-IP rate limit on `/query` |

CloudFront adds an `X-Origin-Secret` header to every request it forwards.
When `ORIGIN_SECRET` is set, the backend returns 403 to requests without it,
so calling the Railway domain directly doesn't get past CloudFront. `/health`
is exempt for Railway's healthcheck.

**Do the steps in order.** Setting `ORIGIN_SECRET` before CloudFront exists
gets every request a 403.

---

## 1. Apply the Terraform

`<railway-domain>` is the backend's domain under **Service Settings →
Networking → Public Networking**, without `https://`.

```sh
cd terraform/backend_edge
terraform init
terraform apply -var origin_domain=<railway-domain>
```

The distribution takes a few minutes to deploy.

## 2. Check CloudFront reaches the backend

```sh
curl "$(terraform output -raw api_url)/health"   # {"status":"ok"}
```

## 3. Turn on the origin guard

Railway → backend service → **Variables** → `ORIGIN_SECRET` = output of:

```sh
terraform output -raw origin_secret
```

Railway redeploys. Then:

```sh
curl -X POST "$(terraform output -raw api_url)/query"   # 401: passed the guard, no token
curl -X POST https://<railway-domain>/query             # 403: skipped CloudFront
```

## 4. Point the UI at CloudFront

Vercel → UI project → **Settings → Environment Variables** →
`NEXT_PUBLIC_API_URL` = `terraform output -raw api_url`, then redeploy.
`NEXT_PUBLIC_*` values are inlined at build time, so a redeploy is required.

Log in and run a query to confirm.

---

## Rotating the secret

```sh
terraform apply -replace=random_password.origin_secret -var origin_domain=<railway-domain>
```

Then update `ORIGIN_SECRET` on Railway. Requests get 403 between the two
steps, so do them back to back.

## Tuning

- `query_rate_limit` (default 100 per IP per minute): campus users can share
  an IP, so keep it well above one user's rate.
- WAF metrics: CloudWatch (us-east-1) → Metrics → WAFV2 → `backend-edge`.

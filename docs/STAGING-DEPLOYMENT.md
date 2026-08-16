# LEGAL AI BUREAU — Staging Deployment Guide

Companion to `docs/STAGING-DEPLOYMENT-AUDIT.md` (what was found) and this document (what to actually do). This deploys a **test/staging** environment for external testers — not production. Local development (`docker compose up`) is unaffected by anything here.

## 0. Prerequisite: push this repository to a git remote

Both Vercel and Render deploy from a git remote (GitHub/GitLab/Bitbucket) in their standard flow. This repository was `git init`'d locally as part of this pass but has no remote and no commits yet — that's a decision for you, not something done automatically.

```bash
cd E:\Проекты\legal-ai-bureau
git add -A
git commit -m "Initial commit"
```
Then create an empty repository on GitHub (or your host of choice) and:
```bash
git remote add origin <your-repo-url>
git push -u origin main
```

## 1. Neon (PostgreSQL + pgvector)

1. Create a Neon project (neon.tech) — any region close to your Render region.
2. Neon gives you a connection string shaped like:
   `postgresql://user:password@ep-xxxx.region.aws.neon.tech/neondb?sslmode=require`
3. Rewrite it for this app: change `postgresql://` to `postgresql+asyncpg://`. Leave `?sslmode=require` as-is — the app rewrites `sslmode` to asyncpg's expected `ssl` automatically at connection time (`app/db/session.py::_normalize_database_url`, see audit §8). Result:
   `postgresql+asyncpg://user:password@ep-xxxx.region.aws.neon.tech/neondb?sslmode=require`
4. Copy this as `DATABASE_URL` for the backend (Render env var, see §3).
5. pgvector: `migrations/versions/0001_initial_schema.py` runs `CREATE EXTENSION IF NOT EXISTS vector` as part of `alembic upgrade head` — Neon supports this extension on all plans, no manual step needed. **Not independently verified against a real Neon project this session** (no credentials available) — confirm this succeeds the first time you run the migration (§5 below); if it fails, Neon's extension allowlist is the first thing to check.

## 2. S3-compatible object storage

Any S3-compatible provider works (AWS S3, Cloudflare R2, Backblaze B2, ...). Steps for AWS S3 (adapt for others):

1. Create a bucket (e.g. `legal-ai-bureau-staging`). Keep it **private** — the app is the only thing that reads/writes it, there's no public URL serving.
2. Create an IAM user (or R2/B2 API token) with `PutObject`/`GetObject`/`DeleteObject`/`HeadObject` scoped to that bucket only.
3. Collect: bucket name, access key id, secret access key, region, and (for non-AWS providers) the S3-compatible endpoint URL.
4. These map directly to the backend env vars in §3: `STORAGE_PROVIDER=s3`, `STORAGE_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_REGION`, `S3_ENDPOINT_URL` (leave blank for real AWS S3; required for R2/B2/MinIO/etc).

## 3. Render (backend web service)

**Option A — Blueprint** (`render.yaml` at the repo root): in the Render dashboard, "New +" → "Blueprint" → point at your git remote. Render reads `render.yaml` and proposes the service. You'll still need to fill in every `sync: false` env var manually in the dashboard (secrets are never stored in the blueprint file) — see the checklist in §7.

**Option B — Manual web service** (if the Blueprint's exact fields don't match Render's current UI):
1. "New +" → "Web Service" → connect your git remote.
2. Runtime: **Docker**. Dockerfile path: `infra/docker/backend.Dockerfile`. Docker build context: repository root (`.`).
3. Health check path: `/ready`.
4. Add every env var from the checklist in §7.
5. Deploy.

Either way:
- The Dockerfile's `CMD` already binds `0.0.0.0:$PORT` (Render injects `$PORT` at runtime; falls back to 8000 only for local `docker compose`, which never sets it) — see `docs/STAGING-DEPLOYMENT-AUDIT.md` §4.
- Migrations: `render.yaml`'s `preDeployCommand` runs `alembic upgrade head` before each deploy is routed traffic. If your Render plan/UI doesn't expose "Pre-Deploy Command", run it manually instead (§5) before the very first deploy, then re-run it manually after any future migration until you confirm the field works for your plan.

## 4. Vercel (frontend)

1. "Add New" → "Project" → import your git remote, root directory `frontend/`.
2. Vercel auto-detects Next.js — no build command changes needed (no `vercel.json` required; this is a standard App Router app, confirmed in the audit — no `output: "export"`, so SSR and dynamic routes deploy natively).
3. Add env vars (Project Settings → Environment Variables):
   - `NEXT_PUBLIC_API_BASE_URL` = your Render backend URL (e.g. `https://legal-ai-bureau-backend.onrender.com`)
   - `NEXT_PUBLIC_STAGING_BANNER` = `true`
   - `NEXT_PUBLIC_FEEDBACK_URL` = wherever you want "Report an issue" clicks to go (an issue tracker URL, a `mailto:` link, a form — your choice)
4. Deploy. Direct-refresh on any route (`/documents/[id]`, `/cases/[id]`, etc.) works natively — no rewrites config needed.
5. Copy the resulting `https://<project>.vercel.app` URL — you need it for the backend's `CORS_ALLOWED_ORIGINS` (§7), then redeploy the backend (or just update the env var — Render restarts on env var change) so the browser's CORS preflight actually succeeds.

## 5. Migrations — exact command

Run once against the real Neon database before (or via `preDeployCommand`, automatically on) the first deploy:

```bash
cd backend
DATABASE_URL="postgresql+asyncpg://user:password@ep-xxxx.region.aws.neon.tech/neondb?sslmode=require" poetry run alembic upgrade head
```

This is non-destructive and idempotent — safe to re-run. `alembic current` shows what's applied:

```bash
DATABASE_URL="..." poetry run alembic current
```

Never run `alembic downgrade` against the staging database as part of routine deployment — that's a deliberate, manual, reversible-only-with-care operation, not part of this guide's flow.

## 6. Staging user seed — exact command

```bash
cd backend
DATABASE_URL="postgresql+asyncpg://user:password@ep-xxxx.region.aws.neon.tech/neondb?sslmode=require" poetry run python -m app.cli.seed_staging_users --with-demo-data
```

Prints 3 sets of credentials (Owner / Lawyer / Viewer roles) to stdout **exactly once** — copy them immediately, they cannot be recovered afterward (only reset by deleting the user row and re-running). Safe to re-run: existing users are left alone. `--with-demo-data` additionally seeds one synthetic demo `Case`, clearly labeled "(synthetic)" in its title/party names — omit the flag to skip it.

## 7. Environment variable checklist (names only — never actual secrets here)

### Backend (Render)
| Variable | Notes |
|---|---|
| `ENVIRONMENT` | `staging` — NOT `development` (disables the safety checks below) |
| `DEBUG` | `false` |
| `LOG_LEVEL` | `INFO` |
| `DATABASE_URL` | Neon connection string, see §1 |
| `JWT_SECRET` | Real random value — Render's `generateValue: true` handles this if using the Blueprint |
| `AUTH_DEV_MODE` | `false` |
| `LLM_PROVIDER` | `mock` (until real Anthropic/OpenAI keys are supplied and live-verified) |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | Only if `LLM_PROVIDER` is set to a real provider |
| `EMBEDDING_PROVIDER` | `mock` (same caveat) |
| `STORAGE_PROVIDER` | `s3` |
| `STORAGE_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_REGION`, `S3_ENDPOINT_URL` | See §2 |
| `CORS_ALLOWED_ORIGINS` | Your Vercel URL + any localhost dev origins you still want, comma-separated |
| `REDIS_URL` | Not required — see audit §6. Only set this if you provision Render Key-Value for a future feature that actually needs it |

### Frontend (Vercel)
| Variable | Notes |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | Your Render backend URL |
| `NEXT_PUBLIC_STAGING_BANNER` | `true` |
| `NEXT_PUBLIC_FEEDBACK_URL` | Your issue-tracker/mailto/form URL |

## 8. Smoke test — exact flow

Once all of the above is live:

1. Open the Vercel URL. Confirm the amber "TEST ENVIRONMENT" banner is visible.
2. Log in with one of the seeded testers' credentials (§6).
3. Confirm the dashboard loads ("Backend: ok").
4. Create a case.
5. Upload a `.txt` document (any short text works — see `docs/PHASE-9-3-LITIGATION-RESULT.md` for the exact adversarial fixture used in prior local smoke tests if you want to reproduce the contradiction-detection walkthrough).
6. Confirm the document reaches `READY` status.
7. Ask it an explicit amount/date question (e.g. "Какая сумма к оплате указана в документе?") — confirm an `EXTRACTED` answer, not "insufficient evidence", if the document contains one.
8. Attach the document to a contract; run Analyze.
9. Open the case's Litigation tabs (Facts/Timeline/Evidence) and confirm they populate.
10. Refresh the browser on a deep route (e.g. `/documents/<id>`) — confirm it loads directly, not a 404.
11. Log out, log back in as a second tester — confirm you only see that tester's own workspace data (cross-workspace isolation — the two seeded testers share one workspace by design; to test true cross-tenant isolation, run `seed_staging_users.py` a second time after manually editing `_WORKSPACE_NAME`, or rely on the automated tenant-isolation test suite, which already covers this against real Postgres).

If every step above works, staging is genuinely usable for external testers — not just "deployed."

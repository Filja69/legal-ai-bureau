# LEGAL AI BUREAU — Staging Deployment Readiness Audit

Scope: identify every local-only assumption blocking a public staging deployment (Vercel + Render + Neon + S3-compatible storage), before writing any deployment code. Nothing in this document has been fixed yet — see `docs/STAGING-DEPLOYMENT.md` for what was actually changed and the current status of each item.

## 1. No git repository

`E:\Проекты\legal-ai-bureau` is not a git repository at all (`git status` → `fatal: not a git repository`). Both Vercel and Render's standard, recommended deploy flow connects to a git remote (GitHub/GitLab/Bitbucket) and auto-deploys on push — this is the very first blocker, before any of the platform-specific config below matters. **This must be resolved by the user** (create a GitHub repo, push this code) since it requires their own git hosting account; a local `git init` is safe and was performed as part of this pass, but the remote + push step is a manual action (see final report).

## 2. `CORS_ALLOWED_ORIGINS` crashes at startup if set as a plain string

`app/config/settings.py` declares `cors_allowed_origins: list[str]`. Pydantic-settings' default environment-variable decoding for any complex (non-scalar) field type attempts **JSON parsing first** — confirmed empirically this session: setting `CORS_ALLOWED_ORIGINS=https://foo.vercel.app,http://localhost:3000` (the natural way to fill in an env var in any cloud dashboard) raises `pydantic_settings.exceptions.SettingsError` and the app fails to boot. Only a JSON array string (`["https://foo.vercel.app","http://localhost:3000"]`) worked before this pass — undocumented and easy to get wrong under time pressure while configuring Render. **Fixed this pass** — see §"Fixed" below.

## 3. `ENVIRONMENT` safety gates only trigger on the literal string `"production"`

Three places key off `settings.environment`:
- `Settings.assert_production_safe()` (JWT-secret-insecure-default check, DEBUG=true check) — returns early unless `environment == "production"`.
- `get_current_user()`'s dev-bypass path — only blocked when `environment == "production"`.
- `configure_logging()`'s JSON-vs-console log renderer choice — only JSON when `environment == "production"`.

If a staging deployment sets `ENVIRONMENT=staging` (a reasonable, honest value to distinguish it from real production), **every one of these safety checks silently does not apply** — the insecure default JWT secret would be accepted, `AUTH_DEV_MODE=true` left over from a copied `.env` would work, and logs would render in human-readable console format instead of structured JSON. **Fixed this pass** by flipping the logic to "development is the only lax value" — anything else (`production`, `staging`, a typo) is treated strictly.

## 4. Backend Dockerfile hardcodes port 8000, incompatible with Render's `$PORT`

`infra/docker/backend.Dockerfile`'s `CMD` used exec form (`CMD ["uvicorn", ..., "--port", "8000"]`), which does not perform shell variable substitution — `$PORT` (the port Render injects at runtime, not fixed) would never be read. **Fixed this pass** — shell-form CMD with `${PORT:-8000}` fallback for local `docker compose` use, which never sets `PORT`.

## 5. Document storage is local-filesystem-only, with no abstraction

`app/documents/storage/local_storage.py` is three free functions (`save_bytes`, `read_bytes`, `delete_file`) writing directly to `var/documents/{workspace_id}/{document_id}{suffix}` on local disk. Render's filesystem is ephemeral — any file written there is lost on redeploy, restart, or scale event. There was no `DocumentStorage` abstraction to swap in an S3-compatible backend, even though `Settings.storage_provider`/`storage_bucket` fields already existed (declared but never read by any code). **Fixed this pass** — see §8 of the deployment doc.

## 6. Redis: declared dependency, zero actual usage

Confirmed via `grep -rn "redis" app/` — the only two hits are `Settings.redis_url` (declared, unread) and a code comment in `app/security/rate_limit.py` explicitly documenting that rate limiting is deliberately in-process/in-memory, *not* Redis-backed, because "Redis... has zero actual usage anywhere in this codebase today... a single-process in-memory limiter is the correct-sized fix for the current single-instance deployment." Celery is also a declared-but-unused dependency (`pyproject.toml`), confirmed in the Phase 9.2 Reality Matrix as `NOT_IMPLEMENTED (dead dependency)`.

**Conclusion for staging**: Redis is not required for any current functional path. `/ready` does not need to (and should not) gate on it. Provisioning Render Key-Value is optional for this initial staging deployment — recommended to skip it initially to reduce cost/complexity, and add it back the moment a real feature needs it (e.g. a distributed rate limiter, or Celery actually gets used). Documented explicitly rather than silently omitted.

## 7. `/ready` doesn't check schema readiness

`GET /ready` (in `app/main.py`) checks DB connectivity (`SELECT 1`) but not whether migrations have actually been applied. A freshly-provisioned, unmigrated Neon database would report `ready` even though every query against application tables would fail. **Fixed this pass** — added a check that `alembic_version` has at least one row.

## 8. Neon requires `ssl=`, not `sslmode=`, for the asyncpg driver

Neon's dashboard gives connection strings with `?sslmode=require` (the libpq/psycopg convention). SQLAlchemy's asyncpg dialect parses query-string SSL configuration under the key `ssl`, not `sslmode` — passing `sslmode=require` through unchanged is silently ignored by asyncpg (not an error, just no SSL enforcement, or in some asyncpg versions an outright connection failure depending on Neon's enforcement). **Fixed this pass** — `get_engine()` now normalizes `sslmode=` to `ssl=` in the configured `DATABASE_URL` before creating the engine, so a raw copy-pasted Neon connection string (rewritten only to add the `+asyncpg` driver prefix, documented in the deployment guide) works without the user needing to know this detail.

## 9. `CREATE EXTENSION vector` — already handled

`migrations/versions/0001_initial_schema.py` already runs `CREATE EXTENSION IF NOT EXISTS vector` (and `uuid-ossp`), idempotently, as part of `alembic upgrade head`. Neon supports the pgvector extension on all plans. No code change needed here — flagged only because the brief asked for explicit verification; this cannot be fully confirmed without running the actual migration against a real Neon database, which requires credentials this session does not have (see final report's blockers).

## 10. Frontend — no local-only assumptions found

- `frontend/lib/api-client.ts` is the single source of truth for the backend base URL: `process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8010"` (dev-only fallback). Confirmed via full-tree grep — no other file references `localhost` or hardcodes an API URL.
- `next.config.js` has no `output: "export"` — this is a standard SSR/App-Router Next.js app, which Vercel deploys natively; direct-refresh on any dynamic route (`/documents/[id]`, `/cases/[id]`, etc.) works without any rewrites configuration.
- Auth (`lib/api-client.ts` request/response interceptors) reads the bearer token and workspace id from client-side state (`lib/auth-store.ts`) and attaches them to every request regardless of backend origin — nothing here assumes same-origin; it already depends on CORS being configured correctly server-side (see §2/§3 above).
- `infra/docker/frontend.Dockerfile` runs `npm run dev` — this is a **local Docker convenience only**, not a production build, and is not part of the Vercel deploy path (Vercel builds directly from the repository with its own pipeline, ignoring this Dockerfile entirely). No change needed; noted so it's not mistaken for a production artifact.

## 11. Admin/debug routes — already correctly protected

`POST /search/debug` and every `/knowledge/*` route (`list_knowledge_sources`, `sync_knowledge_source`, `list_knowledge_documents`, `reindex_knowledge_document`, `knowledge_index_status`, `reindex_knowledge_base`) already require `Depends(require_role(RoleName.ADMIN))`. `AUTH_DEV_MODE`'s bypass is already gated to non-production and requires explicit opt-in (see §3 for the "staging" gap that was fixed). No route was found that exposes credentials or bypasses tenant isolation. Confirmed, no change needed beyond the `ENVIRONMENT` string-matching fix in §3.

## 12. No secret/credential values found in any log call site

Grepped every `logger.info/warning/error/debug(...)` call across `app/` for `token`/`password` — the only two hits (`app/security/deps.py`) log a `reason` string (`"invalid_or_expired_token"`, `"invalid_token_subject"`), never the actual token or password value. Confirmed safe as-is.

## 13. No `boto3` (or any S3 client) dependency yet

Needed to implement `S3DocumentStorage` (§5). Added this pass as a plain dependency (not conditionally installed) — consistent with how `anthropic`/`openai` SDKs are already unconditional dependencies even though `LLM_PROVIDER=mock` is the default; the import is lazy (inside the class, only reached when `STORAGE_PROVIDER=s3` is actually selected), matching the existing lazy-import convention in `app/llm/routing/gateway.py`'s `_build_provider()`.

## Summary — fixed this pass vs. requires manual cloud action

| Item | Status |
|---|---|
| No git repo | `git init` done locally; **push to a remote is a manual user action** |
| CORS env-var parsing crash | Fixed (accepts comma-separated OR JSON array) |
| `ENVIRONMENT` safety-gate gap for "staging" | Fixed (development-only laxity) |
| Dockerfile hardcoded port | Fixed (`$PORT` with local fallback) |
| No storage abstraction / ephemeral Render disk | Fixed (`DocumentStorage` protocol, Local + S3) |
| Redis unused | Documented — recommend skipping for initial staging |
| `/ready` doesn't check schema | Fixed (checks `alembic_version` has rows) |
| Neon `sslmode` vs `ssl` | Fixed (URL normalization in `get_engine()`) |
| pgvector extension | Already handled; **cannot verify against real Neon without credentials** |
| Frontend env/routing | Already correct, no change needed |
| Admin route protection | Already correct, no change needed |
| Secret logging | Already safe, no change needed |

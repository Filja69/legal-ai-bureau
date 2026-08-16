# LEGAL AI BUREAU — Security & Multi-Tenancy Model

Legal documents are among the most sensitive data a user will hand this system — contracts with real financial terms, litigation strategy, corporate ownership. Security is a first-class architectural layer, not a hardening pass at the end.

## 1. Multi-tenancy (brief §37)

```
Organization
 └── Users (role-scoped)
      └── Workspace
           └── Cases / Contracts / Companies / Documents
```

Roles (brief §37): `Owner`, `Admin`, `Lawyer`, `Paralegal`, `Analyst`, `Client`, `Viewer`.

| Role | Can generate documents | Can view all case data | Can invite users | Can view billing |
|---|---|---|---|---|
| Owner | ✓ | ✓ | ✓ | ✓ |
| Admin | ✓ | ✓ | ✓ | ✓ |
| Lawyer | ✓ | ✓ | – | – |
| Paralegal | – (drafts only, review-gated) | ✓ | – | – |
| Analyst | – | ✓ (read) | – | – |
| Client | – | ✓ (only cases explicitly shared with them) | – | – |
| Viewer | – | ✓ (read-only) | – | – |

## 2. Tenant isolation

- Every tenant-scoped table carries `workspace_id` (see [LEGAL-DATABASE.md](LEGAL-DATABASE.md) §5). Enforced two ways, not one:
  1. **ORM-level**: a base repository class injects `WHERE workspace_id = :current_workspace` on every query; direct unscoped queries against tenant tables are a lint-checked violation (custom Ruff rule or code-review gate), not just a convention.
  2. **Postgres row-level security (RLS)** as defense in depth: policies on tenant tables keyed to a session-local `app.current_workspace_id` set per request. A bug in application-layer scoping does not become a cross-tenant data leak.
- The shared public Legal Knowledge Base (`LegalDocument`, `Article`, `CourtDecision`, etc. — [LEGAL-DATABASE.md](LEGAL-DATABASE.md) §2) has no `workspace_id` — it's intentionally global/read-only to all tenants, and is the *only* class of table exempt from RLS tenant scoping.

## 3. Encryption

- **At rest**: Postgres volume encryption (deploy-level, matches `jarvis`'s existing Docker volume setup) + column-level encryption (via `cryptography`, already a `jarvis` dependency) for the most sensitive fields: `CompanyProfile` financial figures, `Contract` party financial terms, uploaded raw document blobs in object storage.
- **In transit**: TLS everywhere (frontend↔API, API↔worker via Redis/Celery over TLS in prod, API↔external legal sources).
- **Secrets**: never in git — env-based (`.env`, matching `jarvis` convention) in dev, a secrets manager in prod. No API keys/DB credentials in code or in prompt templates.

## 4. RBAC enforcement point

RBAC checks live in `backend/app/security/` as FastAPI dependencies applied per-route (`Depends(require_role("lawyer"))`), not scattered `if user.role ==` checks inside business logic — keeps the permission model auditable in one place and matches the pattern already in `jarvis/apps/backend/src/middleware/auth_middleware.py`.

## 5. Audit log (brief §38)

Every AI action and every document/case mutation writes an `AuditLogEntry` (schema: [LEGAL-DATABASE.md](LEGAL-DATABASE.md) §6) recording who, what, when, on which document, which model + prompt version, which sources were used, and the result summary. Written by a single interceptor (API middleware + agent-execution wrapper), not per-agent, so it can't be silently skipped when a new agent is added.

## 6. No training on client data (brief §36, §70)

- Client documents and case content are never sent to any model-provider fine-tuning/training pipeline.
- Where the LLM provider offers a "don't train on this data" API flag (Anthropic/OpenAI enterprise terms), it is set unconditionally for all legal-content calls — enforced centrally in `LLMGateway`, not per call site.
- Client documents never get written into the shared public Knowledge Base (`LegalDocument`/`EmbeddingChunk` global tables) — `UserDocumentSource` ingestion writes only to tenant-scoped tables (LEGAL-SOURCES.md §6).

## 7. Retention, export, deletion

- Configurable per-organization retention policy on `AuditLogEntry` and `GeneratedDocument` history (default: retain for the life of the workspace + a compliance grace period, deletable by Owner/Admin).
- Full workspace export (documents, research reports, audit log) available on request — implemented as an async job (Celery), not a synchronous endpoint, given potential data volume.
- Deletion is soft-delete first (recoverable window) then hard purge on a schedule — mirrors the "don't delete destructively" discipline this system itself is built to respect, applied to its own data.

## 8. Document permissions

Documents can be shared narrower than workspace-wide (e.g., a `Case` shared with a specific `Client` role user, or a `Contract` restricted to `Lawyer`+`Owner`). Modeled as a `DocumentPermission(document_id, principal_id, level)` join table, checked alongside the coarser role check — role gives a ceiling, document-level permission can narrow it further, never widen it.

## 9. Backups

Standard Postgres logical backups (matches `jarvis`'s existing `postgres_data` volume + backup approach — see `jarvis_backup_2026-08-06.sql` precedent) scheduled and encrypted at rest, tested restore path documented in `infrastructure/`.

## 10. Phase 6.5 audit note — the tenant-isolation guarantee has two halves, only one is built

`app/security/deps.py::get_workspace_id()` currently trusts the raw `X-Workspace-Id` request header verbatim — it does **not** verify the calling user (from `get_current_user()`, itself a deterministic dev-identity stub, see the same file's docstring) actually belongs to that workspace. This has been a documented `TODO(Phase 2)` in the code since Task #10; this audit is flagging it explicitly at the architecture-doc level too, since Phase 6.5 §9 asked for a tenant-isolation audit and this is the load-bearing gap in it.

**What IS guaranteed today** (verified — `tests/security/test_tenant_isolation.py`, 7 passing tests as of Phase 6.5): given a `workspace_id`, every `WorkspaceScopedRepository` query (`Case`, `Contract`, and everything else built on that base class) can only see/write rows in that exact workspace — a repository bug cannot leak another tenant's rows. The shared public Legal Knowledge Base (`LawVersion`, `LegalSource`, `EmbeddingChunk`) structurally has no `workspace_id` column at all, verified by test, so "a tenant document silently enters the public KB" isn't a possible bug class, not just an unwritten one — and no code path writes tenant content (contracts, cases) into those tables (`LegalChunkIndexer` is only ever instantiated from `app/api/v1/knowledge.py`'s admin sync/reindex routes).

**What is NOT guaranteed today**: nothing stops a caller from sending someone else's real `X-Workspace-Id` and reading/writing that workspace's data — there is no check that the header matches a workspace the authenticated principal actually belongs to, because there is no real authentication yet (`get_current_user()` mints a fresh random dev identity on every call). This is real auth/authorization work (JWT verification + a `WorkspaceMembership` check), which is a new feature, not a hardening fix, and is out of Phase 6.5's explicit scope ("НЕ добавлять новую бизнес-функциональность"). It must be built before this system holds more than one real tenant's data.

## 11. Phase 7 revision note — the gap in §10 is closed

`get_current_user()` now performs real JWT verification (`app/security/jwt.py`, `python-jose`, HS256 by default — algorithm/secret/issuer/audience/expiry all configurable via `JWT_*` env vars, never hardcoded) against a real `User` row (`app/models/organization.py` — `User`/`WorkspaceMembership`/`Role` already existed in the schema since Task #10's initial migration, just never wired into enforcement until now). `get_workspace_id()` now requires a real `WorkspaceMembership(user_id, workspace_id)` row — `X-Workspace-Id` is a *request*, not proof of access. "Workspace doesn't exist" and "workspace exists but caller isn't a member" return the identical `403` (never `404`) specifically to prevent workspace-id enumeration.

**Dev bypass** (`AUTH_DEV_MODE`, default `false`): when `true` *and* `ENVIRONMENT != production`, a request with **no** `Authorization` header gets a deterministic dev identity — convenience for local development and the pre-Phase-7 test suite, never a weakening of real token validation. A **malformed** (non-`Bearer`) `Authorization` header is always a hard `401`, even under dev mode — the bypass is for absent credentials, not invalid ones. A production deployment with `AUTH_DEV_MODE=true` accidentally left in a shared `.env` still enforces real auth, because the `ENVIRONMENT != production` check is unconditional.

**RBAC**: the existing 7-role `RoleName` enum (`viewer < client < analyst < paralegal < lawyer < admin < owner`) is unchanged. `require_role()` (used by the non-workspace-scoped `/knowledge/*` admin routes) now resolves a real "best role across the caller's workspace memberships" instead of trusting a stub — a user with zero memberships has no role and always fails closed.

**New**: `POST /api/v1/legal/auth/token` (email+password → JWT; bcrypt via `passlib`, already a pinned dependency). Not a full account-management product — no reset flow, no email verification — deliberately minimal per brief §8.

**Verified live** (not just under test): a real user/workspace/membership was created directly in the dev Postgres instance, a token issued via `/auth/token`, and confirmed: own-workspace access → 200, foreign-workspace access with the same token → 403, admin-gated `/search/debug` for an OWNER-role membership → 200. Test data was deleted afterward.

**Dependency fix found in the process**: `passlib` 1.7.4 (unmaintained since 2020) is incompatible with `bcrypt>=4.1` (dropped `__about__`, stricter 72-byte enforcement) — pinned `bcrypt<4.1` in `pyproject.toml`.

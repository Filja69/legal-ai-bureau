"""DocumentStorage abstraction — staging deployment audit §5.

Render's (and most PaaS) filesystem is ephemeral: anything written to local
disk is lost on redeploy, restart, or scale event. `local_storage.py`'s
free functions worked fine for local development but had no swap-in point
for a durable, S3-compatible backend — this module is that swap-in point.

`Settings.storage_provider` ("local" | "s3", already declared before this
pass, just never read by any code) selects the implementation via
`get_document_storage()`. Both implementations return an opaque string
"storage key" from `put()` — a local filesystem path for
`LocalDocumentStorage`, an S3 object key for `S3DocumentStorage` — stored
unchanged in `Document.storage_path` either way, so callers never need to
know which backend produced it.
"""
from __future__ import annotations

import uuid
from typing import Protocol

from app.config.settings import get_settings


class DocumentStorage(Protocol):
    async def put(self, workspace_id: uuid.UUID, document_id: uuid.UUID, content: bytes, *, suffix: str) -> str:
        """Stores `content`, returns an opaque storage key to persist on `Document.storage_path`."""
        ...

    async def get(self, storage_key: str) -> bytes: ...

    async def delete(self, storage_key: str) -> None: ...

    async def exists(self, storage_key: str) -> bool: ...


class DocumentStorageConfigError(RuntimeError):
    """STORAGE_PROVIDER is set to something this app doesn't implement.
    Never silently falls back to local storage — a deployment that asked
    for S3 and mistyped the provider name must fail loudly, not discover
    later that uploads were quietly landing on ephemeral local disk.
    """


class DocumentStorageError(RuntimeError):
    """A storage backend failed at RUNTIME (bad credentials, unreachable
    endpoint, disk full, permission denied, ...) — distinct from
    `DocumentStorageConfigError`, which is a boot-time misconfiguration.
    Raised by `LocalDocumentStorage`/`S3DocumentStorage` with a message
    that never includes credential values, bucket contents, or raw
    provider tracebacks — safe to log and safe to derive a user-facing
    detail from. The P0 production incident this exists for: an uncaught
    `botocore` exception from `S3DocumentStorage.put()` propagated past
    `CORSMiddleware` (Starlette's `ServerErrorMiddleware` sits OUTSIDE it —
    see app/api/v1/documents.py's upload handler for the full explanation),
    so the browser reported a misleading "CORS blocked" error for what was
    actually an unhandled storage failure. Catching this exception INSIDE
    the route handler and converting it to a real `HTTPException` is what
    lets the response flow through `ExceptionMiddleware` -> `CORSMiddleware`
    normally, with CORS headers intact.
    """


def get_document_storage() -> DocumentStorage:
    settings = get_settings()
    if settings.storage_provider == "local":
        from app.documents.storage.local_storage import LocalDocumentStorage

        return LocalDocumentStorage()
    if settings.storage_provider == "s3":
        from app.documents.storage.s3_storage import S3DocumentStorage

        return S3DocumentStorage(
            bucket=settings.storage_bucket,
            endpoint_url=settings.s3_endpoint_url,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
            region=settings.s3_region,
        )
    raise DocumentStorageConfigError(f"STORAGE_PROVIDER={settings.storage_provider!r} is not implemented (local|s3).")

"""Local filesystem storage backend (STORAGE_PROVIDER=local, .env.example)
— the default, used by local development.

Phase 9.2 (brief §7): the original filename is NEVER used as a filesystem
path component — a client can send anything as `filename` (including
`../../secret`, an absolute path, or Unicode path tricks), so the on-disk
path is built entirely from server-generated identifiers
(`workspace_id`/`document_id`) plus a validated extension. The original
filename is preserved only as metadata (`Document.original_filename`).
This guarantee doesn't depend on WHERE `_STORAGE_ROOT` points — every path
component under it is always a server-generated UUID, never client input,
whether the root is the repo-relative dev default or an operator-configured
persistent Volume mount path.

Content/size/type validation happens in `app/documents/validation.py`
before this module is ever called — this module trusts its caller already
validated `content`.

Staging deployment audit §5: refactored from three free functions into a
`LocalDocumentStorage` class implementing `DocumentStorage` (see base.py)
so `S3DocumentStorage` can be swapped in via `STORAGE_PROVIDER=s3` without
call sites caring which backend they're talking to. The on-disk path shape
is unchanged from before this refactor — existing local `var/documents/`
files continue to resolve correctly.

P0 follow-up (Railway persistent Volume): `_STORAGE_ROOT`'s default value
now comes from `Settings.local_storage_path` (env `LOCAL_STORAGE_PATH`) —
set it to a mounted Volume's path so uploads survive redeploys/restarts,
which a bare container filesystem does not guarantee. Left unset, behavior
is byte-for-byte the same repo-relative `var/documents/` path as before
this option existed. Deliberately NOT hardcoded to any specific platform's
mount path (e.g. `/data/documents`) — the operator supplies that via the
env var, so this module stays portable across hosts.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from app.documents.storage.base import DocumentStorageError

_DEFAULT_STORAGE_ROOT = Path(__file__).resolve().parents[3] / "var" / "documents"


def _resolve_storage_root() -> Path:
    from app.config.settings import get_settings

    configured = get_settings().local_storage_path
    return Path(configured) if configured else _DEFAULT_STORAGE_ROOT


# Computed once at import time (settings are already loaded from the
# environment by then, same convention as e.g. embedding_chunk.py's
# _EMBEDDING_DIMENSION) — tests override this module attribute directly via
# monkeypatch (unchanged pattern, see tests/unit/test_document_storage.py),
# not by re-triggering this resolution after import.
_STORAGE_ROOT = _resolve_storage_root()

# Matches the suffixes `app/documents/validation.py` allows — enforced again
# here as defense-in-depth so this module can never be made to write an
# arbitrary path component even if a caller forgot to validate first.
_ALLOWED_SUFFIXES = {".pdf", ".docx", ".txt", ".xlsx", ".csv", ".png", ".jpg", ".jpeg"}


def _safe_suffix(suffix: str) -> str:
    if suffix not in _ALLOWED_SUFFIXES:
        raise ValueError(f"Refusing to store a file with an unrecognized suffix: {suffix!r}")
    return suffix


class LocalDocumentStorage:
    async def put(self, workspace_id: uuid.UUID, document_id: uuid.UUID, content: bytes, *, suffix: str) -> str:
        """Path shape: var/documents/{workspace_id}/{document_id}{suffix} — every
        path component after the storage root is a server-generated UUID, never
        client input, so path traversal and duplicate-filename collisions are
        both structurally impossible (brief §7).
        """
        suffix = _safe_suffix(suffix)
        workspace_dir = _STORAGE_ROOT / str(workspace_id)
        path = workspace_dir / f"{document_id}{suffix}"
        try:
            workspace_dir.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        except OSError as exc:
            raise DocumentStorageError(f"local disk write failed ({type(exc).__name__})") from exc
        return str(path)

    async def get(self, storage_key: str) -> bytes:
        return Path(storage_key).read_bytes()

    async def delete(self, storage_key: str) -> None:
        path = Path(storage_key)
        if path.exists():
            path.unlink()

    async def exists(self, storage_key: str) -> bool:
        return Path(storage_key).exists()

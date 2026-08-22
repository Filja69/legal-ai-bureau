"""DocumentStorage abstraction — staging deployment audit §5. Local backend
behavior is unit-tested directly; S3 backend is unit-tested against a mocked
boto3 client (no real S3-compatible endpoint needed for these). Live S3
behavior is exercised manually as part of the staging smoke test (see
docs/STAGING-DEPLOYMENT.md) since it requires real bucket credentials.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.documents.storage.base import DocumentStorageConfigError, DocumentStorageError, get_document_storage
from app.documents.storage.local_storage import LocalDocumentStorage


@pytest.mark.asyncio
async def test_local_storage_put_get_roundtrip(tmp_path, monkeypatch):
    import app.documents.storage.local_storage as local_storage_module

    monkeypatch.setattr(local_storage_module, "_STORAGE_ROOT", tmp_path)
    storage = LocalDocumentStorage()
    workspace_id, document_id = uuid.uuid4(), uuid.uuid4()

    key = await storage.put(workspace_id, document_id, b"hello world", suffix=".txt")
    assert await storage.get(key) == b"hello world"
    assert await storage.exists(key) is True


@pytest.mark.asyncio
async def test_local_storage_get_missing_file_raises_document_storage_error(tmp_path, monkeypatch):
    """Found while validating OCR reprocessing (P0): get() previously let a
    raw FileNotFoundError escape uncaught — unlike put(), and unlike
    S3DocumentStorage.get(), which already wrapped read failures. A missing
    file on the Volume (or any other on-disk read failure) must surface as
    the same honest DocumentStorageError put() already raises, not a raw
    exception that reaches the API layer unguarded.
    """
    import app.documents.storage.local_storage as local_storage_module

    monkeypatch.setattr(local_storage_module, "_STORAGE_ROOT", tmp_path)
    storage = LocalDocumentStorage()

    with pytest.raises(DocumentStorageError):
        await storage.get(str(tmp_path / "nonexistent" / "does_not_exist.pdf"))


@pytest.mark.asyncio
async def test_local_storage_delete(tmp_path, monkeypatch):
    import app.documents.storage.local_storage as local_storage_module

    monkeypatch.setattr(local_storage_module, "_STORAGE_ROOT", tmp_path)
    storage = LocalDocumentStorage()
    workspace_id, document_id = uuid.uuid4(), uuid.uuid4()

    key = await storage.put(workspace_id, document_id, b"content", suffix=".txt")
    await storage.delete(key)
    assert await storage.exists(key) is False


@pytest.mark.asyncio
async def test_local_storage_exists_false_for_missing_key(tmp_path, monkeypatch):
    import app.documents.storage.local_storage as local_storage_module

    monkeypatch.setattr(local_storage_module, "_STORAGE_ROOT", tmp_path)
    storage = LocalDocumentStorage()
    assert await storage.exists(str(tmp_path / "nonexistent" / "nope.txt")) is False


@pytest.mark.asyncio
async def test_local_storage_never_uses_client_filename_as_path_component(tmp_path, monkeypatch):
    """Phase 9.2 brief §7, re-verified after the storage refactor: the
    on-disk path is built entirely from server-generated UUIDs. A
    path-traversal-shaped original filename is never involved — `put()`
    doesn't even accept a filename parameter, only a validated suffix.
    """
    import app.documents.storage.local_storage as local_storage_module

    monkeypatch.setattr(local_storage_module, "_STORAGE_ROOT", tmp_path)
    storage = LocalDocumentStorage()
    workspace_id, document_id = uuid.uuid4(), uuid.uuid4()

    key = await storage.put(workspace_id, document_id, b"content", suffix=".txt")
    assert ".." not in key
    assert str(document_id) in key
    assert str(workspace_id) in key


@pytest.mark.asyncio
async def test_local_storage_rejects_unrecognized_suffix(tmp_path, monkeypatch):
    import app.documents.storage.local_storage as local_storage_module

    monkeypatch.setattr(local_storage_module, "_STORAGE_ROOT", tmp_path)
    storage = LocalDocumentStorage()
    with pytest.raises(ValueError, match="unrecognized suffix"):
        await storage.put(uuid.uuid4(), uuid.uuid4(), b"content", suffix=".exe")


# --- get_document_storage() factory ---


def test_factory_defaults_to_local_storage(monkeypatch):
    monkeypatch.delenv("STORAGE_PROVIDER", raising=False)
    from app.config.settings import get_settings

    get_settings.cache_clear()
    storage = get_document_storage()
    assert isinstance(storage, LocalDocumentStorage)
    get_settings.cache_clear()


def test_factory_raises_for_s3_without_bucket(monkeypatch):
    monkeypatch.setenv("STORAGE_PROVIDER", "s3")
    monkeypatch.delenv("STORAGE_BUCKET", raising=False)
    from app.config.settings import get_settings

    get_settings.cache_clear()
    with pytest.raises(DocumentStorageConfigError, match="STORAGE_BUCKET"):
        get_document_storage()
    get_settings.cache_clear()
    monkeypatch.delenv("STORAGE_PROVIDER", raising=False)


def test_factory_raises_for_unknown_provider(monkeypatch):
    monkeypatch.setenv("STORAGE_PROVIDER", "azure-blob")
    from app.config.settings import get_settings

    get_settings.cache_clear()
    with pytest.raises(DocumentStorageConfigError, match="not implemented"):
        get_document_storage()
    get_settings.cache_clear()
    monkeypatch.delenv("STORAGE_PROVIDER", raising=False)


# --- S3DocumentStorage — unit-tested against a mocked boto3 client ---


def _s3_storage_with_mock_client():
    from app.documents.storage.s3_storage import S3DocumentStorage

    with patch("boto3.client") as mock_client_factory:
        mock_client = MagicMock()
        mock_client_factory.return_value = mock_client
        storage = S3DocumentStorage(
            bucket="test-bucket", endpoint_url=None, access_key_id="key", secret_access_key="secret", region="us-east-1"
        )
        return storage, mock_client


@pytest.mark.asyncio
async def test_s3_storage_put_uses_workspace_document_key_shape():
    storage, mock_client = _s3_storage_with_mock_client()
    workspace_id, document_id = uuid.uuid4(), uuid.uuid4()

    key = await storage.put(workspace_id, document_id, b"content", suffix=".pdf")

    assert key == f"{workspace_id}/{document_id}.pdf"
    mock_client.put_object.assert_called_once_with(Bucket="test-bucket", Key=key, Body=b"content")


@pytest.mark.asyncio
async def test_s3_storage_get_reads_object_body():
    storage, mock_client = _s3_storage_with_mock_client()
    mock_body = MagicMock()
    mock_body.read.return_value = b"stored content"
    mock_client.get_object.return_value = {"Body": mock_body}

    result = await storage.get("workspace/document.pdf")

    assert result == b"stored content"
    mock_client.get_object.assert_called_once_with(Bucket="test-bucket", Key="workspace/document.pdf")


@pytest.mark.asyncio
async def test_s3_storage_delete_calls_delete_object():
    storage, mock_client = _s3_storage_with_mock_client()
    await storage.delete("workspace/document.pdf")
    mock_client.delete_object.assert_called_once_with(Bucket="test-bucket", Key="workspace/document.pdf")


def test_s3_storage_requires_bucket():
    from app.documents.storage.s3_storage import S3DocumentStorage

    with pytest.raises(DocumentStorageConfigError, match="STORAGE_BUCKET"):
        S3DocumentStorage(bucket=None, endpoint_url=None, access_key_id=None, secret_access_key=None, region="us-east-1")


def test_s3_storage_never_uses_client_filename_original_as_key():
    """Same brief §7 guarantee as local storage — the key is built from
    workspace_id/document_id only, put() has no filename parameter at all.
    """
    storage, _ = _s3_storage_with_mock_client()
    key = storage._key(uuid.uuid4(), uuid.uuid4(), ".txt")
    assert ".." not in key


# --- P0 production incident regression: a raw botocore/OSError exception
# must never escape put()/get()/delete() uncaught — see DocumentStorageError's
# docstring for why an uncaught exception here broke CORS on the response. ---


@pytest.mark.asyncio
async def test_s3_storage_put_wraps_client_exception_in_document_storage_error():
    storage, mock_client = _s3_storage_with_mock_client()
    mock_client.put_object.side_effect = RuntimeError("AccessDenied: invalid credentials for bucket xyz")

    with pytest.raises(DocumentStorageError) as exc_info:
        await storage.put(uuid.uuid4(), uuid.uuid4(), b"content", suffix=".docx")

    # The safe, logged message names the exception TYPE only — never the
    # original botocore message, which could contain bucket/account details.
    assert "RuntimeError" in str(exc_info.value)
    assert "AccessDenied" not in str(exc_info.value)
    assert "invalid credentials" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_s3_storage_get_wraps_client_exception_in_document_storage_error():
    storage, mock_client = _s3_storage_with_mock_client()
    mock_client.get_object.side_effect = RuntimeError("NoSuchKey")

    with pytest.raises(DocumentStorageError):
        await storage.get("workspace/document.pdf")


@pytest.mark.asyncio
async def test_s3_storage_delete_wraps_client_exception_in_document_storage_error():
    storage, mock_client = _s3_storage_with_mock_client()
    mock_client.delete_object.side_effect = RuntimeError("connection reset")

    with pytest.raises(DocumentStorageError):
        await storage.delete("workspace/document.pdf")


# --- Railway persistent Volume follow-up: LOCAL_STORAGE_PATH ---


def test_resolve_storage_root_defaults_to_repo_relative_path_when_unset(monkeypatch):
    import app.documents.storage.local_storage as local_storage_module
    from app.config.settings import get_settings

    monkeypatch.delenv("LOCAL_STORAGE_PATH", raising=False)
    get_settings.cache_clear()
    try:
        assert local_storage_module._resolve_storage_root() == local_storage_module._DEFAULT_STORAGE_ROOT
    finally:
        get_settings.cache_clear()


def test_resolve_storage_root_honors_configured_path(monkeypatch):
    import app.documents.storage.local_storage as local_storage_module
    from app.config.settings import get_settings

    monkeypatch.setenv("LOCAL_STORAGE_PATH", "/data/documents")
    get_settings.cache_clear()
    try:
        assert local_storage_module._resolve_storage_root() == local_storage_module.Path("/data/documents")
    finally:
        monkeypatch.delenv("LOCAL_STORAGE_PATH", raising=False)
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_local_storage_put_get_roundtrip_with_custom_configured_root(tmp_path, monkeypatch):
    """The actual Railway scenario: LOCAL_STORAGE_PATH set to a persistent
    Volume's mount path, put() then get() both go through it correctly.
    """
    import app.documents.storage.local_storage as local_storage_module

    custom_root = tmp_path / "persistent-volume-mount"
    monkeypatch.setattr(local_storage_module, "_STORAGE_ROOT", custom_root)
    storage = LocalDocumentStorage()
    workspace_id, document_id = uuid.uuid4(), uuid.uuid4()

    assert not custom_root.exists()  # directory doesn't exist yet — proves auto-creation, not a pre-made fixture dir
    key = await storage.put(workspace_id, document_id, b"loan agreement content", suffix=".docx")

    assert custom_root.exists()  # created automatically
    assert key.startswith(str(custom_root))
    assert await storage.get(key) == b"loan agreement content"


@pytest.mark.asyncio
async def test_local_storage_delete_with_custom_configured_root(tmp_path, monkeypatch):
    import app.documents.storage.local_storage as local_storage_module

    custom_root = tmp_path / "persistent-volume-mount"
    monkeypatch.setattr(local_storage_module, "_STORAGE_ROOT", custom_root)
    storage = LocalDocumentStorage()
    workspace_id, document_id = uuid.uuid4(), uuid.uuid4()

    key = await storage.put(workspace_id, document_id, b"content", suffix=".txt")
    assert await storage.exists(key) is True
    await storage.delete(key)
    assert await storage.exists(key) is False


@pytest.mark.asyncio
async def test_local_storage_path_traversal_impossible_with_custom_configured_root(tmp_path, monkeypatch):
    """Same brief §7 guarantee re-verified specifically against a
    Volume-style configured root, not just the dev default — every path
    component past the root is still a server-generated UUID.
    """
    import app.documents.storage.local_storage as local_storage_module

    custom_root = tmp_path / "persistent-volume-mount"
    monkeypatch.setattr(local_storage_module, "_STORAGE_ROOT", custom_root)
    storage = LocalDocumentStorage()
    workspace_id, document_id = uuid.uuid4(), uuid.uuid4()

    key = await storage.put(workspace_id, document_id, b"content", suffix=".txt")

    resolved = local_storage_module.Path(key).resolve()
    assert str(custom_root.resolve()) in str(resolved)
    assert ".." not in key
    # The file must land exactly one level below the workspace directory,
    # never anywhere else under (or worse, outside) the configured root.
    assert resolved.parent == (custom_root / str(workspace_id)).resolve()


@pytest.mark.asyncio
async def test_local_storage_put_wraps_os_error_in_document_storage_error(tmp_path, monkeypatch):
    import app.documents.storage.local_storage as local_storage_module

    # A file (not a directory) at the workspace path makes mkdir(parents=True,
    # exist_ok=True) raise a real OSError/NotADirectoryError — a realistic
    # analogue of "disk full"/"permission denied" without needing root or a
    # full filesystem to actually reproduce.
    blocked_root = tmp_path / "blocked"
    blocked_root.write_bytes(b"not a directory")
    monkeypatch.setattr(local_storage_module, "_STORAGE_ROOT", blocked_root)
    storage = LocalDocumentStorage()

    with pytest.raises(DocumentStorageError):
        await storage.put(uuid.uuid4(), uuid.uuid4(), b"content", suffix=".txt")

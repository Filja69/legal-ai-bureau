"""S3-compatible object storage backend (STORAGE_PROVIDER=s3) — staging
deployment audit §5/§9. Talks to any S3-compatible endpoint (not just AWS —
`S3_ENDPOINT_URL` lets this point at any provider that speaks the S3 API),
so the domain layer never binds directly to AWS-specific assumptions.

Object key shape: `{workspace_id}/{document_id}{suffix}` — deliberately
identical in structure to `LocalDocumentStorage`'s on-disk path (minus the
storage-root prefix), so the same path-traversal-proof reasoning applies:
every key component is a server-generated UUID, never the client-supplied
original filename.

boto3 is a synchronous SDK; each call here runs in a worker thread via
`asyncio.to_thread` so a slow S3 request never blocks the event loop for
every other in-flight request on this process — unlike the local backend's
disk I/O (already an accepted trade-off there), a network call is enough
latency to matter. Imported lazily inside `__init__`, matching the same
lazy-import convention `app/llm/routing/gateway.py::_build_provider` and
`app/rag/embeddings/base.py::get_embedding_provider` already use for
optional real-provider SDKs — `boto3` is only ever imported when
`STORAGE_PROVIDER=s3` is actually selected.
"""
from __future__ import annotations

import asyncio
import uuid

from app.documents.storage.base import DocumentStorageConfigError


class S3DocumentStorage:
    def __init__(
        self,
        *,
        bucket: str | None,
        endpoint_url: str | None,
        access_key_id: str | None,
        secret_access_key: str | None,
        region: str,
    ) -> None:
        if not bucket:
            raise DocumentStorageConfigError("STORAGE_PROVIDER=s3 but STORAGE_BUCKET is not set.")

        import boto3  # noqa: PLC0415 — lazy, see module docstring

        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
        )

    def _key(self, workspace_id: uuid.UUID, document_id: uuid.UUID, suffix: str) -> str:
        return f"{workspace_id}/{document_id}{suffix}"

    async def put(self, workspace_id: uuid.UUID, document_id: uuid.UUID, content: bytes, *, suffix: str) -> str:
        key = self._key(workspace_id, document_id, suffix)
        await asyncio.to_thread(self._client.put_object, Bucket=self._bucket, Key=key, Body=content)
        return key

    async def get(self, storage_key: str) -> bytes:
        response = await asyncio.to_thread(self._client.get_object, Bucket=self._bucket, Key=storage_key)
        return await asyncio.to_thread(response["Body"].read)

    async def delete(self, storage_key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=storage_key)

    async def exists(self, storage_key: str) -> bool:
        from botocore.exceptions import ClientError  # noqa: PLC0415 — lazy, see module docstring

        try:
            await asyncio.to_thread(self._client.head_object, Bucket=self._bucket, Key=storage_key)
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
                return False
            raise

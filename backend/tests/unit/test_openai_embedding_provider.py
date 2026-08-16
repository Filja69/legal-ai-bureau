"""OpenAIEmbeddingProvider — Phase 6 brief §1/§14/§16. All tests are offline
(the OpenAI SDK client is monkeypatched) — no real API key or network call
required for the ordinary test suite (brief §64: live-provider tests are
opt-in, never required for CI without credentials).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.rag.embeddings.base import EmbeddingDimensionError, EmbeddingProviderError, embedding_namespace
from app.rag.embeddings.openai_provider import OpenAIEmbeddingProvider


def _fake_response(vectors: list[list[float]]) -> SimpleNamespace:
    return SimpleNamespace(data=[SimpleNamespace(embedding=v) for v in vectors])


def test_missing_api_key_fails_fast():
    with pytest.raises(EmbeddingProviderError, match="OPENAI_API_KEY"):
        OpenAIEmbeddingProvider(api_key="")


@pytest.mark.asyncio
async def test_embed_empty_list_short_circuits():
    provider = OpenAIEmbeddingProvider(api_key="sk-test", dimensions=4)
    assert await provider.embed([]) == []


@pytest.mark.asyncio
async def test_embed_batches_requests(monkeypatch):
    provider = OpenAIEmbeddingProvider(api_key="sk-test", dimensions=3, batch_size=2)
    calls: list[list[str]] = []

    async def fake_create(*, model, input, dimensions):
        calls.append(list(input))
        return _fake_response([[0.1, 0.2, 0.3] for _ in input])

    provider._client.embeddings.create = fake_create  # type: ignore[method-assign]

    vectors = await provider.embed(["a", "b", "c", "d", "e"])

    assert len(vectors) == 5
    assert [len(c) for c in calls] == [2, 2, 1]  # batch_size=2 over 5 inputs


@pytest.mark.asyncio
async def test_embed_rejects_wrong_dimension_vector():
    provider = OpenAIEmbeddingProvider(api_key="sk-test", dimensions=1536)

    async def fake_create(*, model, input, dimensions):
        return _fake_response([[0.1, 0.2]])  # wrong dimension on purpose

    provider._client.embeddings.create = fake_create  # type: ignore[method-assign]

    with pytest.raises(EmbeddingDimensionError):
        await provider.embed(["text"])


@pytest.mark.asyncio
async def test_embed_rejects_empty_vector():
    provider = OpenAIEmbeddingProvider(api_key="sk-test", dimensions=3)

    async def fake_create(*, model, input, dimensions):
        return _fake_response([[0.0, 0.0, 0.0]])

    provider._client.embeddings.create = fake_create  # type: ignore[method-assign]

    with pytest.raises(EmbeddingProviderError, match="empty/all-zero"):
        await provider.embed(["text"])


@pytest.mark.asyncio
async def test_embed_rejects_mismatched_batch_size_response():
    provider = OpenAIEmbeddingProvider(api_key="sk-test", dimensions=3)

    async def fake_create(*, model, input, dimensions):
        return _fake_response([[0.1, 0.2, 0.3]])  # only 1 vector for 2 inputs

    provider._client.embeddings.create = fake_create  # type: ignore[method-assign]

    with pytest.raises(EmbeddingProviderError, match="returned 1 vectors"):
        await provider.embed(["a", "b"])


@pytest.mark.asyncio
async def test_embed_wraps_transport_failure(monkeypatch):
    provider = OpenAIEmbeddingProvider(api_key="sk-test", dimensions=3)
    provider._client.embeddings.create = AsyncMock(side_effect=TimeoutError("boom"))  # type: ignore[method-assign]

    with pytest.raises(EmbeddingProviderError, match="TimeoutError"):
        await provider.embed(["text"])


def test_embedding_namespace_distinguishes_provider_model_and_dimensions():
    provider_a = OpenAIEmbeddingProvider(api_key="sk-test", model="text-embedding-3-small", dimensions=1536)
    provider_b = OpenAIEmbeddingProvider(api_key="sk-test", model="text-embedding-3-large", dimensions=1536)
    provider_c = OpenAIEmbeddingProvider(api_key="sk-test", model="text-embedding-3-small", dimensions=512)

    assert embedding_namespace(provider_a) == "openai:text-embedding-3-small:1536"
    assert embedding_namespace(provider_a) != embedding_namespace(provider_b)
    assert embedding_namespace(provider_a) != embedding_namespace(provider_c)

"""get_embedding_provider() — Phase 6 brief §1/§20: never silently falls
back to mock when a real provider was configured but misconfigured/missing
credentials. All offline — no real network calls.
"""
from __future__ import annotations

import pytest

from app.config.settings import Settings
from app.rag.embeddings.base import EmbeddingProviderError, MockEmbeddingProvider, get_embedding_provider
from app.rag.embeddings.openai_provider import OpenAIEmbeddingProvider


def _settings(**overrides) -> Settings:
    return Settings(**overrides)


def test_mock_provider_by_default(monkeypatch):
    monkeypatch.setattr("app.rag.embeddings.base.get_settings", lambda: _settings())
    provider = get_embedding_provider()
    assert isinstance(provider, MockEmbeddingProvider)


def test_openai_without_api_key_fails_fast_never_falls_back_to_mock(monkeypatch):
    monkeypatch.setattr(
        "app.rag.embeddings.base.get_settings",
        lambda: _settings(embedding_provider="openai", openai_api_key=None),
    )
    with pytest.raises(EmbeddingProviderError, match="OPENAI_API_KEY"):
        get_embedding_provider()


def test_openai_with_api_key_builds_real_provider(monkeypatch):
    monkeypatch.setattr(
        "app.rag.embeddings.base.get_settings",
        lambda: _settings(embedding_provider="openai", openai_api_key="sk-test", embedding_dimension=1536),
    )
    provider = get_embedding_provider()
    assert isinstance(provider, OpenAIEmbeddingProvider)
    assert provider.model_name == "text-embedding-3-small"
    assert provider.dimensions == 1536


def test_unknown_provider_raises_not_mock(monkeypatch):
    monkeypatch.setattr("app.rag.embeddings.base.get_settings", lambda: _settings(embedding_provider="not-a-real-provider"))
    with pytest.raises(EmbeddingProviderError):
        get_embedding_provider()

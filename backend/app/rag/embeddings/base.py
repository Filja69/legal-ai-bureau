"""EmbeddingProvider interface (LEGAL-DATABASE.md §2 EmbeddingChunk, brief §21-22)."""
from __future__ import annotations

import hashlib
from typing import Protocol

from app.config.settings import get_settings


class EmbeddingProviderError(RuntimeError):
    """A real provider failed, timed out, or returned something unusable.

    Never caught and silently turned into a mock/empty result — the caller
    must see the embedding step failed (Phase 6 brief §14), not proceed as
    if nothing happened.
    """


class EmbeddingDimensionError(EmbeddingProviderError):
    """A provider returned a vector whose length doesn't match its declared
    `dimensions` — always rejected, never truncated/padded to fit."""


class EmbeddingProvider(Protocol):
    model_name: str
    dimensions: int
    provider_name: str  # "mock" | "openai" | ... — the namespace key (brief §21-22)
    model_version: str | None  # provider-reported revision, if any; None if not exposed

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


def embedding_namespace(provider: EmbeddingProvider) -> str:
    """The identity key vectors are compared within (brief §2/§22) — two
    providers, two models, or two dimension counts are never one namespace,
    even if e.g. the model name happens to collide.
    """
    return f"{provider.provider_name}:{provider.model_name}:{provider.dimensions}"


class MockEmbeddingProvider:
    """Deterministic pseudo-embeddings — same input text always produces the
    same vector, and different texts produce different (but semantically
    meaningless) vectors. This is enough to exercise the pgvector column,
    cosine-similarity ranking, and hybrid-merge logic end to end without a
    real embedding API key. It is NOT semantic search — see the Phase 2
    report's REAL/MOCK split.
    """

    def __init__(self, dimensions: int | None = None) -> None:
        self.model_name = "mock-embedding-v1"
        self.dimensions = dimensions or get_settings().embedding_dimension
        self.provider_name = "mock"
        self.model_version: str | None = None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        # Expand a SHA-256 digest with a counter to fill `dimensions` floats,
        # then L2-normalize so cosine similarity behaves sanely.
        values: list[float] = []
        counter = 0
        while len(values) < self.dimensions:
            digest = hashlib.sha256(f"{text}:{counter}".encode()).digest()
            values.extend(b / 255.0 - 0.5 for b in digest)
            counter += 1
        values = values[: self.dimensions]
        norm = sum(v * v for v in values) ** 0.5 or 1.0
        return [v / norm for v in values]


def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    if settings.embedding_provider == "mock":
        return MockEmbeddingProvider(settings.embedding_dimension)
    if settings.embedding_provider == "openai":
        if not settings.openai_api_key:
            # Fail fast, never silently fall back to mock (Phase 6 brief §1/§20)
            # — a production deployment that asked for real embeddings and
            # didn't get them must know immediately, not discover it later
            # as an unexplained retrieval-quality regression.
            raise EmbeddingProviderError(
                "EMBEDDING_PROVIDER=openai but OPENAI_API_KEY is not set. "
                "Set OPENAI_API_KEY in the environment (see .env.example) — "
                "this never silently falls back to MockEmbeddingProvider."
            )
        from app.rag.embeddings.openai_provider import OpenAIEmbeddingProvider

        return OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key,
            model=settings.embedding_model if settings.embedding_model != "mock-embedding-v1" else "text-embedding-3-small",
            dimensions=settings.embedding_dimension,
            batch_size=settings.embedding_batch_size,
            timeout_seconds=settings.embedding_timeout_seconds,
            max_retries=settings.embedding_max_retries,
            max_requests_per_minute=settings.embedding_max_requests_per_minute,
        )
    raise EmbeddingProviderError(f"Embedding provider {settings.embedding_provider!r} is not implemented yet.")

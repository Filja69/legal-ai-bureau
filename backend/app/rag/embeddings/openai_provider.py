"""OpenAIEmbeddingProvider — the only file in the codebase allowed to
`from openai import ...` for embeddings (mirrors app/llm/providers/openai_provider.py's
"one file per SDK" rule, LEGAL-RAG.md §9 revision note).

Real, batched, timeout-bounded, retryable — but never silently degrades:
a wrong-dimension or empty vector from the API is rejected outright rather
than indexed as if it were valid (Phase 6 brief §14 "Failure modes").
Retry/backoff is delegated to the OpenAI SDK's own `max_retries`/`timeout`
(it already implements exponential backoff for 429/5xx) rather than a
second, parallel retry framework.
"""
from __future__ import annotations

import asyncio
import time

import structlog

from app.rag.embeddings.base import EmbeddingDimensionError, EmbeddingProviderError

logger = structlog.get_logger(__name__)


class OpenAIEmbeddingProvider:
    provider_name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
        batch_size: int = 96,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        max_requests_per_minute: int = 500,
    ) -> None:
        from openai import AsyncOpenAI  # local import — keeps the dependency optional for mock-only setups

        if not api_key:
            raise EmbeddingProviderError(
                "OpenAIEmbeddingProvider requires an API key. Set OPENAI_API_KEY in the environment "
                "(see .env.example) — no key was supplied, and no mock fallback happens here."
            )

        self._client = AsyncOpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=max_retries)
        self.model_name = model
        self.dimensions = dimensions
        self.model_version: str | None = None  # OpenAI's embeddings API does not expose a separate revision string
        self._batch_size = batch_size
        self._min_seconds_between_requests = 60.0 / max_requests_per_minute if max_requests_per_minute > 0 else 0.0
        self._last_request_at: float | None = None

    async def _throttle(self) -> None:
        # A simple fixed-interval throttle (Phase 6.5 brief §3 cost protection)
        # — not a token-bucket, just enough to guarantee this process can
        # never exceed max_requests_per_minute against a real paid API,
        # independent of the SDK's own retry/backoff on 429s.
        if self._min_seconds_between_requests <= 0 or self._last_request_at is None:
            return
        elapsed = time.monotonic() - self._last_request_at
        wait = self._min_seconds_between_requests - elapsed
        if wait > 0:
            await asyncio.sleep(wait)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        all_vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            await self._throttle()
            self._last_request_at = time.monotonic()
            call_start = time.perf_counter()
            try:
                response = await self._client.embeddings.create(model=self.model_name, input=batch, dimensions=self.dimensions)
            except Exception as exc:  # noqa: BLE001 — re-raised as our own typed error, never swallowed
                logger.info(
                    "embedding_failure", provider=self.provider_name, model=self.model_name, batch_size=len(batch),
                    latency_ms=round((time.perf_counter() - call_start) * 1000, 2), error_type=type(exc).__name__,
                )
                raise EmbeddingProviderError(f"OpenAI embeddings request failed ({type(exc).__name__}): {exc}") from exc

            if len(response.data) != len(batch):
                raise EmbeddingProviderError(
                    f"OpenAI embeddings response returned {len(response.data)} vectors for a batch of {len(batch)} inputs"
                )

            for item in response.data:
                vector = item.embedding
                if len(vector) != self.dimensions:
                    raise EmbeddingDimensionError(
                        f"OpenAI returned a {len(vector)}-dimension vector, expected {self.dimensions} "
                        f"(model={self.model_name!r}) — rejecting rather than indexing a mismatched vector."
                    )
                if not vector or all(v == 0.0 for v in vector):
                    raise EmbeddingProviderError("OpenAI returned an empty/all-zero embedding vector — rejecting.")
                all_vectors.append(vector)

            # Phase 7 brief §22 — call metadata only, never the embedded text
            # itself (may be confidential contract/case content).
            logger.info(
                "embedding_call", provider=self.provider_name, model=self.model_name, batch_size=len(batch),
                latency_ms=round((time.perf_counter() - call_start) * 1000, 2), success=True,
            )

        return all_vectors

"""Real embedding provider smoke test — Phase 6.5 brief §4.

    python -m app.cli.embedding_smoke_test

Verifies a real embedding provider is reachable and behaves as declared,
WITHOUT touching the production Knowledge Base:

    1. credentials present?
    2. provider/model/dimensions/namespace shown
    3. one minimal embedding request sent
    4. returned vector's dimension checked against what the provider declares
    5. namespace computed and shown

It never writes to `embedding_chunks`, never runs `LegalChunkIndexer`, and
never triggers a reindex — this is read-only connectivity verification, not
an ingestion tool. If `EMBEDDING_PROVIDER=mock` or `OPENAI_API_KEY` is
missing, it says so explicitly and exits — it never silently substitutes
mock output for a real test result.
"""
from __future__ import annotations

import asyncio
import sys

from app.config.settings import get_settings
from app.rag.embeddings.base import EmbeddingProviderError, embedding_namespace, get_embedding_provider

_SMOKE_TEXT = "надлежащее исполнение обязательства"  # minimal, single, real-topic string — not a bulk request


def _print(*lines: str) -> None:
    for line in lines:
        print(line)  # noqa: T201 — this is a CLI, stdout is the product


async def main() -> int:
    settings = get_settings()

    if settings.embedding_provider != "openai":
        _print(
            f"EMBEDDING_PROVIDER={settings.embedding_provider!r} (not 'openai')",
            "REAL API TEST NOT RUN",
            "Set EMBEDDING_PROVIDER=openai and OPENAI_API_KEY to exercise a real provider.",
        )
        return 1

    if not settings.openai_api_key:
        _print("OPENAI_API_KEY missing", "REAL API TEST NOT RUN")
        return 1

    try:
        provider = get_embedding_provider()
    except EmbeddingProviderError as exc:
        _print(f"Provider construction failed: {exc}", "REAL API TEST NOT RUN")
        return 1

    _print(
        f"Provider: {provider.provider_name}",
        f"Model: {provider.model_name}",
        f"Dimensions (configured): {provider.dimensions}",
        f"Namespace: {embedding_namespace(provider)}",
    )

    try:
        [vector] = await provider.embed([_SMOKE_TEXT])
    except EmbeddingProviderError as exc:
        _print(f"API connectivity: FAILED ({exc})", "Embedding generation: FAILED", "Production indexing: NOT RUN")
        return 1

    _print("API connectivity: OK", "Embedding generation: OK")

    if len(vector) != provider.dimensions:
        _print(
            f"Dimension check: FAILED (got {len(vector)}, expected {provider.dimensions})",
            "Production indexing: NOT RUN",
        )
        return 1
    _print(f"Dimension check: OK ({len(vector)})")

    _print(
        "Production indexing: NOT RUN",
        "Reindex: NOT RUN",
        "This command never writes to the Knowledge Base — see LEGAL-RAG.md Phase 6.5 revision note.",
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

"""LLMGateway — task-class based provider/model routing (LEGAL-ARCHITECTURE.md §4).

Agents call `gateway.generate(task_class=..., ...)`, never a provider directly.
This is what makes the two-lawyer principle (LEGAL-AGENTS.md §5) structural:
TaskClass.REVIEW is configured to resolve to a different provider/model
identity than TaskClass.GENERATION for the same request.

Phase 7 (brief §10-13): `structured_generate` now owns the shared
LLM -> raw response -> JSON extraction -> schema validation -> repair/retry
-> typed result pipeline for every provider, so AnthropicProvider/
OpenAIProvider only need to get *some* JSON out of their SDK — schema
conformance and retry/repair live here, once, not duplicated per provider.
"""
from __future__ import annotations

import asyncio
import enum
import time
from typing import Any

import jsonschema
import structlog

from app.config.settings import Settings, get_settings
from app.llm.base import LLMMessage, LLMProvider, LLMResponse

logger = structlog.get_logger(__name__)


class TaskClass(str, enum.Enum):
    CLASSIFICATION = "classification"
    EXTRACTION = "extraction"
    RESEARCH = "research"
    REASONING = "reasoning"
    GENERATION = "generation"
    REVIEW = "review"


class LLMProviderError(RuntimeError):
    """A configured real provider couldn't be built (e.g. missing API key).

    Never caught and silently replaced with MockLLMProvider — a deployment
    that asked for a real provider and didn't get one must fail loudly at
    startup, not discover it later as unexplained mock-quality output
    (mirrors app.rag.embeddings.base.EmbeddingProviderError's contract).
    """


class LLMStructuredGenerationError(RuntimeError):
    """Raised after exhausting retries on invalid/unparseable structured
    output. Fail closed — the domain layer must never receive a partially
    valid or best-effort-repaired dict; either it's schema-valid or this
    is raised (Phase 7 brief §12 "invalid LLM output -> fabricate: нельзя").
    """


# Model routing table — task class -> a cost/capability TIER, not a raw
# model string. _MODEL_BY_PROVIDER_AND_TIER below maps each tier to a real
# model identifier per provider; MockLLMProvider ignores the value entirely.
# (Phase 7 fix: previously the tier name itself — "strong", "strongest" —
# was passed straight through as `model=` to real providers, which would
# have been rejected by the Anthropic/OpenAI API as an unknown model the
# moment a real provider was ever actually used.)
_DEFAULT_MODEL_BY_TASK_CLASS: dict[TaskClass, str] = {
    TaskClass.CLASSIFICATION: "cheap",
    TaskClass.EXTRACTION: "fast",
    TaskClass.RESEARCH: "strong",
    TaskClass.REASONING: "strongest",
    TaskClass.GENERATION: "strong",
    TaskClass.REVIEW: "strongest",
}

_MODEL_BY_PROVIDER_AND_TIER: dict[str, dict[str, str]] = {
    "anthropic": {
        "cheap": "claude-haiku-4-5-20251001",
        "fast": "claude-haiku-4-5-20251001",
        "strong": "claude-sonnet-5",
        "strongest": "claude-opus-5",
    },
    "openai": {
        "cheap": "gpt-4o-mini",
        "fast": "gpt-4o-mini",
        "strong": "gpt-4o",
        "strongest": "gpt-4o",
    },
}


def _resolve_model(provider_name: str, tier_or_explicit_model: str) -> str:
    """A caller passing an explicit real model name (not one of the 4 tier
    names) always wins — this only translates the *default* tier hint."""
    provider_table = _MODEL_BY_PROVIDER_AND_TIER.get(provider_name)
    if provider_table is None:
        return tier_or_explicit_model  # mock (or any future provider without a table): pass through
    return provider_table.get(tier_or_explicit_model, tier_or_explicit_model)


def _build_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "mock":
        from app.llm.providers.mock_provider import MockLLMProvider

        return MockLLMProvider()
    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise LLMProviderError(
                "LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set — this never silently "
                "falls back to MockLLMProvider. Set ANTHROPIC_API_KEY or use LLM_PROVIDER=mock."
            )
        from app.llm.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider(api_key=settings.anthropic_api_key)
    if settings.llm_provider == "openai":
        if not settings.openai_api_key:
            raise LLMProviderError(
                "LLM_PROVIDER=openai but OPENAI_API_KEY is not set — this never silently "
                "falls back to MockLLMProvider. Set OPENAI_API_KEY or use LLM_PROVIDER=mock."
            )
        from app.llm.providers.openai_provider import OpenAIProvider

        return OpenAIProvider(api_key=settings.openai_api_key)
    raise LLMProviderError(f"LLM_PROVIDER={settings.llm_provider!r} is not a recognized provider (mock|anthropic|openai).")


class LLMGateway:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self._provider = provider or _build_provider(get_settings())

    async def generate(self, task_class: TaskClass, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        model_hint = _DEFAULT_MODEL_BY_TASK_CLASS[task_class]
        model = _resolve_model(self._provider.name, kwargs.pop("model", model_hint))
        return await self._provider.generate(messages, model=model, **kwargs)

    async def structured_generate(
        self, task_class: TaskClass, messages: list[LLMMessage], *, response_schema: dict[str, Any], **kwargs
    ) -> dict[str, Any]:
        settings = get_settings()
        model_hint = kwargs.pop("model", _DEFAULT_MODEL_BY_TASK_CLASS[task_class])
        model = _resolve_model(self._provider.name, model_hint)
        current_messages = list(messages)
        last_error: Exception | None = None

        for attempt in range(1, settings.llm_max_retries + 1):
            start = time.perf_counter()
            error_type: str | None = None
            try:
                result = await asyncio.wait_for(
                    self._provider.structured_generate(
                        current_messages, response_schema=response_schema, model=model, **kwargs
                    ),
                    timeout=settings.llm_timeout_seconds,
                )
            except TimeoutError:
                error_type = "timeout"
                last_error = TimeoutError(f"structured_generate timed out after {settings.llm_timeout_seconds}s")
            except Exception as exc:  # noqa: BLE001 — provider/SDK failure, normalized into one retry path
                error_type = type(exc).__name__
                last_error = exc
            else:
                try:
                    jsonschema.validate(result, response_schema)
                except jsonschema.ValidationError as exc:
                    error_type = "schema_violation"
                    last_error = exc
                else:
                    self._log_attempt(task_class, model, attempt, start, success=True, error_type=None)
                    return result

            self._log_attempt(task_class, model, attempt, start, success=False, error_type=error_type)
            if attempt < settings.llm_max_retries:
                current_messages = [
                    *current_messages,
                    LLMMessage(
                        role="user",
                        content=(
                            f"Your previous response was invalid ({error_type}: {last_error}). "
                            "Respond again with ONLY valid JSON that exactly matches the required schema — "
                            "no markdown, no commentary, no extra fields."
                        ),
                    ),
                ]

        raise LLMStructuredGenerationError(
            f"structured_generate failed after {settings.llm_max_retries} attempts (task_class={task_class.value}): {last_error}"
        )

    def _log_attempt(
        self, task_class: TaskClass, model: str, attempt: int, start: float, *, success: bool, error_type: str | None
    ) -> None:
        # Phase 7 brief §13 — never log prompt/message content (may contain
        # confidential contract/case text), only call metadata.
        logger.info(
            "llm_call",
            provider=self._provider.name,
            model=model,
            task_class=task_class.value,
            attempt=attempt,
            latency_ms=round((time.perf_counter() - start) * 1000, 2),
            success=success,
            error_type=error_type,
        )

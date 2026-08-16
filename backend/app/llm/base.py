"""LLMProvider abstraction (LEGAL-ARCHITECTURE.md §4).

No agent, service, or route may `import anthropic` or `from openai import ...`
directly — everything goes through this Protocol + the LLMGateway in
app/llm/routing/gateway.py. This is what lets task-class model routing
(cheap model for classification, strongest for reasoning) and provider
swaps happen in one place.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class LLMMessage:
    role: str  # "user" | "assistant" | "system"
    content: str


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    stop_reason: str = "end_turn"
    usage: dict[str, int] = field(default_factory=dict)
    raw: Any = None


class LLMProvider(Protocol):
    """One implementation per vendor. See app/llm/providers/."""

    name: str

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """Free-text completion."""
        ...

    async def structured_generate(
        self,
        messages: list[LLMMessage],
        *,
        response_schema: dict[str, Any],
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Completion constrained to a JSON schema — used for LegalAgentResult
        and every other structured-output contract in LEGAL-AGENTS.md §7.
        """
        ...

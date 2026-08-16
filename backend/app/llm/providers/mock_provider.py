"""MockLLMProvider — deterministic, no network calls. Default provider until
real credentials are configured (LLM_PROVIDER=mock, see .env.example).
Lets every downstream layer (agents, Research Engine, tests) be built and
exercised without live API keys or network access.
"""
from __future__ import annotations

from typing import Any

from app.llm.base import LLMMessage, LLMResponse


class MockLLMProvider:
    name = "mock"

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        return LLMResponse(
            text=f"[mock-llm] echo: {last_user[:200]}",
            model=model or "mock-echo-1",
            provider=self.name,
        )

    async def structured_generate(
        self,
        messages: list[LLMMessage],
        *,
        response_schema: dict[str, Any],
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Returns a schema-conformant, honestly-EMPTY response — never a
        fabricated legal conclusion. Phase 1 hardcoded one fixed shape here;
        Phase 3's Research Engine has half a dozen different stages
        (fact extraction, issue identification, query generation, reasoning,
        counterargument, review), each with its own schema, so this now
        derives empty-but-valid defaults generically from `response_schema`
        (a JSON-Schema-like dict) instead of special-casing each caller.
        Every caller must treat empty output as "no signal", not "verified
        empty" — the Research Engine's deterministic layers (citation
        validation, confidence, conflict detection) do not depend on this
        producing anything meaningful under LLM_PROVIDER=mock.
        """
        return _empty_value_for_schema(response_schema)


def _empty_value_for_schema(schema: dict[str, Any]) -> Any:
    schema_type = schema.get("type")

    if schema_type == "object" or "properties" in schema:
        return {key: _empty_value_for_schema(subschema) for key, subschema in schema.get("properties", {}).items()}
    if schema_type == "array":
        return []
    if schema_type == "string":
        return ""
    if schema_type in ("number", "integer"):
        return 0
    if schema_type == "boolean":
        return False
    # Unknown/unspecified type — safest empty default without guessing intent.
    return None

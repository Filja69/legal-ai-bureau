"""AnthropicProvider — the only file in the codebase allowed to `import anthropic`."""
from __future__ import annotations

from typing import Any, cast

from app.llm.base import LLMMessage, LLMResponse


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, default_model: str = "claude-sonnet-5") -> None:
        import anthropic  # local import — keeps the dependency optional for mock-only setups

        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._default_model = default_model

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        # LLMMessage.role is a free-form str (validated at the call site to be
        # "user"/"assistant"); the Anthropic SDK wants a literal union here, so
        # we cast rather than pretend the dict is statically that precise.
        anthropic_messages = cast(Any, [{"role": m.role, "content": m.content} for m in messages])
        response = await self._client.messages.create(
            model=model or self._default_model,
            system=system or "",
            max_tokens=max_tokens,
            temperature=temperature,
            messages=anthropic_messages,
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return LLMResponse(
            text=text,
            model=response.model,
            provider=self.name,
            stop_reason=response.stop_reason or "end_turn",
            usage={"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens},
            raw=response,
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
        # Forced tool-use: a single tool whose input_schema IS response_schema,
        # and tool_choice pins the model to calling exactly that tool — this is
        # Anthropic's native structured-output mechanism (far more reliable
        # than asking for JSON in prose and hoping). Schema *validation* and
        # retry/repair live one layer up in LLMGateway (shared across
        # providers) — this method's only job is "get JSON out of Anthropic."
        tool_name = "emit_structured_response"
        anthropic_messages = cast(Any, [{"role": m.role, "content": m.content} for m in messages])
        response = await self._client.messages.create(
            model=model or self._default_model,
            system=system or "",
            max_tokens=4096,
            temperature=temperature,
            messages=anthropic_messages,
            tools=[{"name": tool_name, "description": "Emit the structured response.", "input_schema": response_schema}],
            tool_choice={"type": "tool", "name": tool_name},
        )
        tool_use_block = next((block for block in response.content if block.type == "tool_use"), None)
        if tool_use_block is None:
            raise ValueError("Anthropic response contained no tool_use block for the forced structured-output tool.")
        return cast(dict[str, Any], tool_use_block.input)

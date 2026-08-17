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
        #
        # `temperature` stays in the signature to satisfy the shared LLMProvider
        # Protocol (OpenAIProvider uses it) but is deliberately never forwarded
        # to the Anthropic API. Verified live against platform.claude.com on
        # this audit: Claude Opus 5 (and Opus 4.7/4.8) reject temperature/
        # top_p/top_k outright — any value, including the default — with a 400,
        # and Anthropic's own migration guidance is "the safest migration path
        # is to omit these parameters entirely ... prompting is the recommended
        # way to guide model behavior." Sonnet-tier models are not documented
        # as cleanly (some sources suggest non-default values only 400 there),
        # so rather than track a fragile per-model allowlist that breaks again
        # on the next model release, this provider never sends the parameter
        # for ANY model — omission is documented-safe everywhere, forwarding
        # it is not.
        anthropic_messages = cast(Any, [{"role": m.role, "content": m.content} for m in messages])
        response = await self._client.messages.create(
            model=model or self._default_model,
            system=system or "",
            max_tokens=max_tokens,
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
        # See the identical note in generate() — temperature is never forwarded
        # to the Anthropic API for the same reason.
        tool_name = "emit_structured_response"
        anthropic_messages = cast(Any, [{"role": m.role, "content": m.content} for m in messages])
        response = await self._client.messages.create(
            model=model or self._default_model,
            system=system or "",
            max_tokens=4096,
            messages=anthropic_messages,
            tools=[{"name": tool_name, "description": "Emit the structured response.", "input_schema": response_schema}],
            tool_choice={"type": "tool", "name": tool_name},
        )
        tool_use_block = next((block for block in response.content if block.type == "tool_use"), None)
        if tool_use_block is None:
            raise ValueError("Anthropic response contained no tool_use block for the forced structured-output tool.")
        return cast(dict[str, Any], tool_use_block.input)

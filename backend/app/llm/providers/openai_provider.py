"""OpenAIProvider — the only file in the codebase allowed to `from openai import ...`."""
from __future__ import annotations

from typing import Any, cast

from app.llm.base import LLMMessage, LLMResponse


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, default_model: str = "gpt-4o") -> None:
        from openai import AsyncOpenAI  # local import — keeps the dependency optional for mock-only setups

        self._client = AsyncOpenAI(api_key=api_key)
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
        payload: list[dict[str, str]] = [{"role": "system", "content": system}] if system else []
        payload += [{"role": m.role, "content": m.content} for m in messages]
        response = await self._client.chat.completions.create(
            model=model or self._default_model,
            # LLMMessage.role is a free-form str (validated at the call site to be
            # "user"/"assistant"/"system"); the OpenAI SDK wants a literal union here,
            # so we cast rather than pretend the dict is statically that precise.
            messages=cast(Any, payload),
            temperature=temperature,
            max_tokens=max_tokens,
        )
        choice = response.choices[0]
        return LLMResponse(
            text=choice.message.content or "",
            model=response.model,
            provider=self.name,
            stop_reason=choice.finish_reason or "end_turn",
            usage=(
                {"input_tokens": response.usage.prompt_tokens, "output_tokens": response.usage.completion_tokens}
                if response.usage
                else {}
            ),
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
        import json

        # Native structured-output mode. `strict=False` (not OpenAI's default
        # `strict=True`) deliberately — strict mode additionally requires
        # every schema to set `additionalProperties: false` and mark every
        # property required, which callers writing plain JSON-Schema dicts
        # for MockLLMProvider (LEGAL-AGENTS.md §7 contracts) don't do. Real
        # schema conformance is still enforced — one layer up, in
        # LLMGateway, the same way for every provider — so relaxing this
        # doesn't weaken the actual guarantee.
        payload: list[dict[str, str]] = [{"role": "system", "content": system}] if system else []
        payload += [{"role": m.role, "content": m.content} for m in messages]
        response = await self._client.chat.completions.create(
            model=model or self._default_model,
            messages=cast(Any, payload),
            temperature=temperature,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "structured_response", "schema": response_schema, "strict": False},
            },
        )
        content = response.choices[0].message.content or ""
        try:
            return cast(dict[str, Any], json.loads(content))
        except json.JSONDecodeError as exc:
            raise ValueError(f"OpenAI structured response was not valid JSON: {exc}") from exc

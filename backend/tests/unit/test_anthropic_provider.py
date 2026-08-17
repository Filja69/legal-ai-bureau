"""AnthropicProvider — unit tests, no real network calls.

`AnthropicProvider._client` is always replaced with a fake object exposing an
async `messages.create` after construction (constructing the real
`anthropic.AsyncAnthropic` client does no I/O, so `AnthropicProvider(api_key=...)`
itself is safe to call with a throwaway key in every test below — this is the
same pattern already relied on by
`test_llm_gateway_builds_real_anthropic_provider_when_key_present` in
test_llm_structured_generation.py).

Fake Anthropic response objects use `types.SimpleNamespace` rather than the
real SDK types — `AnthropicProvider` only ever reads `.type`/`.text`/`.input`
off content blocks and `.model`/`.stop_reason`/`.usage.input_tokens`/
`.usage.output_tokens` off the response, so a SimpleNamespace with exactly
those attributes reproduces the real shape without depending on SDK internals.

Missing-API-key coverage lives in test_llm_structured_generation.py
(`test_llm_gateway_fails_fast_when_anthropic_key_missing`) — that path is in
`LLMGateway._build_provider`, not in this class, and this fix doesn't touch it.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from anthropic import APIConnectionError

from app.config.settings import Settings
from app.llm.base import LLMMessage
from app.llm.providers.anthropic_provider import AnthropicProvider
from app.llm.routing import gateway as gateway_module
from app.llm.routing.gateway import LLMGateway, LLMStructuredGenerationError, TaskClass

_SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}


def _provider() -> AnthropicProvider:
    provider = AnthropicProvider(api_key="sk-ant-test-not-a-real-key")
    provider._client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock()))
    return provider


def _fake_response(
    *, content, model: str = "claude-sonnet-5", stop_reason: str = "end_turn", input_tokens: int = 10, output_tokens: int = 5
):
    return SimpleNamespace(
        content=content,
        model=model,
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


# --- generate() -------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_returns_text_model_and_provider_from_a_real_shaped_response():
    provider = _provider()
    response = _fake_response(
        content=[SimpleNamespace(type="text", text="Hello from Claude")],
        model="claude-sonnet-5",
        stop_reason="end_turn",
    )
    provider._client.messages.create.return_value = response

    result = await provider.generate([LLMMessage(role="user", content="Hi")], system="be terse")

    assert result.text == "Hello from Claude"
    assert result.model == "claude-sonnet-5"
    assert result.provider == "anthropic"
    assert result.stop_reason == "end_turn"
    assert result.raw is response


@pytest.mark.asyncio
async def test_generate_never_sends_temperature_to_the_api():
    """The audit finding this session is fixing: Claude Opus 5 (and Opus
    4.7/4.8) reject temperature/top_p/top_k outright, so AnthropicProvider
    must never forward the parameter regardless of what the caller passes."""
    provider = _provider()
    provider._client.messages.create.return_value = _fake_response(
        content=[SimpleNamespace(type="text", text="ok")]
    )

    await provider.generate([LLMMessage(role="user", content="Hi")], temperature=0.9)

    kwargs = provider._client.messages.create.call_args.kwargs
    assert "temperature" not in kwargs
    assert "top_p" not in kwargs
    assert "top_k" not in kwargs


@pytest.mark.asyncio
async def test_generate_passes_model_system_and_max_tokens_through():
    provider = _provider()
    provider._client.messages.create.return_value = _fake_response(content=[SimpleNamespace(type="text", text="ok")])

    await provider.generate(
        [LLMMessage(role="user", content="Hi")], system="sys prompt", model="claude-opus-5", max_tokens=777
    )

    kwargs = provider._client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-opus-5"
    assert kwargs["system"] == "sys prompt"
    assert kwargs["max_tokens"] == 777
    assert kwargs["messages"] == [{"role": "user", "content": "Hi"}]


@pytest.mark.asyncio
async def test_generate_falls_back_to_default_model_when_none_given():
    provider = _provider()
    provider._client.messages.create.return_value = _fake_response(content=[SimpleNamespace(type="text", text="ok")])

    await provider.generate([LLMMessage(role="user", content="Hi")])

    assert provider._client.messages.create.call_args.kwargs["model"] == "claude-sonnet-5"


@pytest.mark.asyncio
async def test_generate_only_concatenates_text_blocks():
    """A non-text block (e.g. a future thinking block) must never be read for
    `.text` — the join expression filters by `block.type == "text"` before
    ever touching `.text`, so a block that lacks that attribute entirely must
    not raise."""
    provider = _provider()
    provider._client.messages.create.return_value = _fake_response(
        content=[
            SimpleNamespace(type="thinking"),  # deliberately has no .text
            SimpleNamespace(type="text", text="Part one. "),
            SimpleNamespace(type="text", text="Part two."),
        ]
    )

    result = await provider.generate([LLMMessage(role="user", content="Hi")])

    assert result.text == "Part one. Part two."


# --- usage parsing ------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_parses_usage_into_a_plain_dict():
    provider = _provider()
    provider._client.messages.create.return_value = _fake_response(
        content=[SimpleNamespace(type="text", text="ok")], input_tokens=123, output_tokens=45
    )

    result = await provider.generate([LLMMessage(role="user", content="Hi")])

    assert result.usage == {"input_tokens": 123, "output_tokens": 45}


# --- structured_generate() / tool_use parsing --------------------------


@pytest.mark.asyncio
async def test_structured_generate_returns_the_tool_use_input_dict():
    provider = _provider()
    provider._client.messages.create.return_value = _fake_response(
        content=[SimpleNamespace(type="tool_use", id="toolu_1", name="emit_structured_response", input={"answer": "42"})]
    )

    result = await provider.structured_generate([LLMMessage(role="user", content="q")], response_schema=_SCHEMA)

    assert result == {"answer": "42"}


@pytest.mark.asyncio
async def test_structured_generate_finds_tool_use_block_even_when_preceded_by_text():
    provider = _provider()
    provider._client.messages.create.return_value = _fake_response(
        content=[
            SimpleNamespace(type="text", text="Let me think about this."),
            SimpleNamespace(type="tool_use", id="toolu_2", name="emit_structured_response", input={"answer": "found it"}),
        ]
    )

    result = await provider.structured_generate([LLMMessage(role="user", content="q")], response_schema=_SCHEMA)

    assert result == {"answer": "found it"}


@pytest.mark.asyncio
async def test_structured_generate_raises_when_no_tool_use_block_present():
    provider = _provider()
    provider._client.messages.create.return_value = _fake_response(
        content=[SimpleNamespace(type="text", text="I decline to call the tool.")]
    )

    with pytest.raises(ValueError, match="no tool_use block"):
        await provider.structured_generate([LLMMessage(role="user", content="q")], response_schema=_SCHEMA)


@pytest.mark.asyncio
async def test_structured_generate_forces_tool_choice_to_the_schema_tool():
    provider = _provider()
    provider._client.messages.create.return_value = _fake_response(
        content=[SimpleNamespace(type="tool_use", id="toolu_1", name="emit_structured_response", input={"answer": "x"})]
    )

    await provider.structured_generate([LLMMessage(role="user", content="q")], response_schema=_SCHEMA)

    kwargs = provider._client.messages.create.call_args.kwargs
    assert kwargs["tool_choice"] == {"type": "tool", "name": "emit_structured_response"}
    assert kwargs["tools"] == [
        {"name": "emit_structured_response", "description": "Emit the structured response.", "input_schema": _SCHEMA}
    ]


@pytest.mark.asyncio
async def test_structured_generate_never_sends_temperature_to_the_api():
    provider = _provider()
    provider._client.messages.create.return_value = _fake_response(
        content=[SimpleNamespace(type="tool_use", id="toolu_1", name="emit_structured_response", input={"answer": "x"})]
    )

    await provider.structured_generate([LLMMessage(role="user", content="q")], response_schema=_SCHEMA, temperature=0.0)

    kwargs = provider._client.messages.create.call_args.kwargs
    assert "temperature" not in kwargs
    assert "top_p" not in kwargs
    assert "top_k" not in kwargs


# --- API errors ----------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_propagates_anthropic_api_errors_uncaught():
    """AnthropicProvider must never swallow a real SDK error — the gateway's
    retry loop (tested separately below) is what's supposed to catch it."""
    provider = _provider()
    provider._client.messages.create.side_effect = APIConnectionError(
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    )

    with pytest.raises(APIConnectionError):
        await provider.generate([LLMMessage(role="user", content="Hi")])


@pytest.mark.asyncio
async def test_structured_generate_propagates_anthropic_api_errors_uncaught():
    provider = _provider()
    provider._client.messages.create.side_effect = APIConnectionError(
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    )

    with pytest.raises(APIConnectionError):
        await provider.structured_generate([LLMMessage(role="user", content="q")], response_schema=_SCHEMA)


# --- timeout/retry through the existing LLMGateway ------------------------


@pytest.mark.asyncio
async def test_gateway_retries_a_real_anthropic_provider_after_a_transient_api_error(monkeypatch):
    monkeypatch.setattr(gateway_module, "get_settings", lambda: Settings(llm_max_retries=3, llm_timeout_seconds=5))
    provider = _provider()
    ok_response = _fake_response(
        content=[SimpleNamespace(type="tool_use", id="toolu_1", name="emit_structured_response", input={"answer": "recovered"})]
    )
    provider._client.messages.create.side_effect = [
        APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")),
        ok_response,
    ]

    gateway = LLMGateway(provider=provider)
    result = await gateway.structured_generate(
        TaskClass.REASONING, [LLMMessage(role="user", content="q")], response_schema=_SCHEMA
    )

    assert result == {"answer": "recovered"}
    assert provider._client.messages.create.call_count == 2


@pytest.mark.asyncio
async def test_gateway_times_out_a_slow_real_anthropic_provider_and_retries_then_fails_closed(monkeypatch):
    monkeypatch.setattr(gateway_module, "get_settings", lambda: Settings(llm_max_retries=2, llm_timeout_seconds=0.01))
    provider = _provider()

    async def _hang(*_args, **_kwargs):
        await asyncio.sleep(1)
        return _fake_response(content=[SimpleNamespace(type="text", text="too slow to matter")])

    provider._client.messages.create.side_effect = _hang

    gateway = LLMGateway(provider=provider)
    with pytest.raises(LLMStructuredGenerationError):
        await gateway.structured_generate(
            TaskClass.REASONING, [LLMMessage(role="user", content="q")], response_schema=_SCHEMA
        )

    assert provider._client.messages.create.call_count == 2  # never exceeds llm_max_retries

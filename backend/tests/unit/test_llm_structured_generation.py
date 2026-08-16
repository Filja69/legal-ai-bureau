"""LLMGateway.structured_generate — Phase 7 brief §10-13. All offline (fake
providers, no real API calls) — exercises the shared JSON-extraction ->
schema-validation -> repair/retry -> fail-closed pipeline that now lives in
LLMGateway itself, once, rather than duplicated per provider.
"""
from __future__ import annotations

import pytest

from app.config.settings import Settings
from app.llm.base import LLMMessage
from app.llm.routing import gateway as gateway_module
from app.llm.routing.gateway import LLMGateway, LLMProviderError, LLMStructuredGenerationError, TaskClass, _resolve_model

_SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}


class _ScriptedProvider:
    """Returns a scripted sequence of results/exceptions, one per call —
    lets a test assert exactly how many attempts happened and in what order.
    """

    name = "scripted"

    def __init__(self, script: list) -> None:
        self._script = list(script)
        self.calls: list[list[LLMMessage]] = []

    async def generate(self, *args, **kwargs):  # pragma: no cover — unused by these tests
        raise NotImplementedError

    async def structured_generate(self, messages, *, response_schema, system=None, model=None, temperature=0.0):
        self.calls.append(list(messages))
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.mark.asyncio
async def test_structured_generate_succeeds_on_first_valid_response(monkeypatch):
    monkeypatch.setattr(gateway_module, "get_settings", lambda: Settings(llm_max_retries=3, llm_timeout_seconds=5))
    provider = _ScriptedProvider([{"answer": "ok"}])
    gateway = LLMGateway(provider=provider)

    result = await gateway.structured_generate(
        TaskClass.REASONING, [LLMMessage(role="user", content="q")], response_schema=_SCHEMA
    )
    assert result == {"answer": "ok"}
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_structured_generate_retries_on_invalid_json_then_succeeds(monkeypatch):
    monkeypatch.setattr(gateway_module, "get_settings", lambda: Settings(llm_max_retries=3, llm_timeout_seconds=5))
    provider = _ScriptedProvider([ValueError("not valid JSON"), {"answer": "recovered"}])
    gateway = LLMGateway(provider=provider)

    result = await gateway.structured_generate(
        TaskClass.REASONING, [LLMMessage(role="user", content="q")], response_schema=_SCHEMA
    )
    assert result == {"answer": "recovered"}
    assert len(provider.calls) == 2
    # The repair attempt's message list must be longer than the original —
    # a correction instruction was appended, not silently retried verbatim.
    assert len(provider.calls[1]) > len(provider.calls[0])


@pytest.mark.asyncio
async def test_structured_generate_retries_on_schema_violation_then_succeeds(monkeypatch):
    monkeypatch.setattr(gateway_module, "get_settings", lambda: Settings(llm_max_retries=3, llm_timeout_seconds=5))
    provider = _ScriptedProvider([{"wrong_key": "oops"}, {"answer": "fixed"}])
    gateway = LLMGateway(provider=provider)

    result = await gateway.structured_generate(
        TaskClass.REASONING, [LLMMessage(role="user", content="q")], response_schema=_SCHEMA
    )
    assert result == {"answer": "fixed"}
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_structured_generate_fails_closed_after_exhausting_retries(monkeypatch):
    monkeypatch.setattr(gateway_module, "get_settings", lambda: Settings(llm_max_retries=2, llm_timeout_seconds=5))
    provider = _ScriptedProvider([ValueError("bad"), ValueError("still bad")])
    gateway = LLMGateway(provider=provider)

    with pytest.raises(LLMStructuredGenerationError):
        await gateway.structured_generate(
            TaskClass.REASONING, [LLMMessage(role="user", content="q")], response_schema=_SCHEMA
        )
    assert len(provider.calls) == 2  # never exceeds llm_max_retries


@pytest.mark.asyncio
async def test_structured_generate_never_returns_invalid_data_even_transiently(monkeypatch):
    """The critical safety property: whatever comes back from
    structured_generate (if it returns at all) is schema-valid — there is
    no code path that returns the wrong_key dict from the middle attempt."""
    monkeypatch.setattr(gateway_module, "get_settings", lambda: Settings(llm_max_retries=3, llm_timeout_seconds=5))
    provider = _ScriptedProvider([{"wrong_key": "oops"}, {"also_wrong": True}, {"answer": "finally"}])
    gateway = LLMGateway(provider=provider)

    result = await gateway.structured_generate(
        TaskClass.REASONING, [LLMMessage(role="user", content="q")], response_schema=_SCHEMA
    )
    assert result == {"answer": "finally"}


@pytest.mark.asyncio
async def test_structured_generate_handles_timeout_as_a_retryable_failure(monkeypatch):
    monkeypatch.setattr(gateway_module, "get_settings", lambda: Settings(llm_max_retries=2, llm_timeout_seconds=0.01))

    class _SlowProvider:
        name = "slow"
        calls = 0

        async def generate(self, *a, **k):  # pragma: no cover
            raise NotImplementedError

        async def structured_generate(self, *a, **k):
            import asyncio

            _SlowProvider.calls += 1
            await asyncio.sleep(1)
            return {"answer": "too slow"}

    gateway = LLMGateway(provider=_SlowProvider())
    with pytest.raises(LLMStructuredGenerationError):
        await gateway.structured_generate(
            TaskClass.REASONING, [LLMMessage(role="user", content="q")], response_schema=_SCHEMA
        )
    assert _SlowProvider.calls == 2


@pytest.mark.asyncio
async def test_structured_generate_logs_never_include_message_content(monkeypatch, capsys):
    monkeypatch.setattr(gateway_module, "get_settings", lambda: Settings(llm_max_retries=1, llm_timeout_seconds=5))
    provider = _ScriptedProvider([{"answer": "ok"}])
    gateway = LLMGateway(provider=provider)

    secret_text = "CONFIDENTIAL-CONTRACT-TERMS-xyz123"
    await gateway.structured_generate(
        TaskClass.REASONING, [LLMMessage(role="user", content=secret_text)], response_schema=_SCHEMA
    )
    out = capsys.readouterr().out
    assert secret_text not in out


def test_resolve_model_maps_tier_to_real_model_for_anthropic():
    assert _resolve_model("anthropic", "strong") == "claude-sonnet-5"
    assert _resolve_model("anthropic", "strongest") == "claude-opus-5"


def test_resolve_model_maps_tier_to_real_model_for_openai():
    assert _resolve_model("openai", "strong") == "gpt-4o"


def test_resolve_model_passes_through_explicit_model_names():
    assert _resolve_model("anthropic", "claude-opus-5-20260101") == "claude-opus-5-20260101"


def test_resolve_model_passes_through_for_mock():
    assert _resolve_model("mock", "strong") == "strong"


def test_llm_gateway_fails_fast_when_anthropic_key_missing(monkeypatch):
    monkeypatch.setattr(
        gateway_module, "get_settings", lambda: Settings(llm_provider="anthropic", anthropic_api_key=None)
    )
    with pytest.raises(LLMProviderError, match="ANTHROPIC_API_KEY"):
        LLMGateway()


def test_llm_gateway_fails_fast_when_openai_key_missing(monkeypatch):
    monkeypatch.setattr(gateway_module, "get_settings", lambda: Settings(llm_provider="openai", openai_api_key=None))
    with pytest.raises(LLMProviderError, match="OPENAI_API_KEY"):
        LLMGateway()


def test_llm_gateway_builds_real_anthropic_provider_when_key_present(monkeypatch):
    monkeypatch.setattr(
        gateway_module, "get_settings", lambda: Settings(llm_provider="anthropic", anthropic_api_key="sk-ant-test")
    )
    gateway = LLMGateway()
    assert gateway._provider.name == "anthropic"


def test_llm_gateway_builds_real_openai_provider_when_key_present(monkeypatch):
    monkeypatch.setattr(gateway_module, "get_settings", lambda: Settings(llm_provider="openai", openai_api_key="sk-test"))
    gateway = LLMGateway()
    assert gateway._provider.name == "openai"

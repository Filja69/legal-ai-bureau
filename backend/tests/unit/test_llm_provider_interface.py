from __future__ import annotations

import pytest

from app.llm.base import LLMMessage
from app.llm.providers.mock_provider import MockLLMProvider
from app.llm.routing.gateway import LLMGateway, TaskClass


@pytest.mark.asyncio
async def test_mock_provider_generate_echoes_input():
    provider = MockLLMProvider()
    response = await provider.generate([LLMMessage(role="user", content="hello legal ai")])
    assert "hello legal ai" in response.text
    assert response.provider == "mock"


@pytest.mark.asyncio
async def test_mock_provider_structured_generate_empty_schema_returns_none():
    provider = MockLLMProvider()
    result = await provider.structured_generate([LLMMessage(role="user", content="q")], response_schema={})
    assert result is None


@pytest.mark.asyncio
async def test_mock_provider_structured_generate_derives_empty_defaults_from_schema():
    provider = MockLLMProvider()
    schema = {
        "type": "object",
        "properties": {
            "conclusion": {"type": "string"},
            "confidence": {"type": "string"},
            "risks": {"type": "array"},
            "citation_coverage": {"type": "number"},
            "escalate_to_human": {"type": "boolean"},
        },
    }
    result = await provider.structured_generate([LLMMessage(role="user", content="q")], response_schema=schema)

    assert result == {
        "conclusion": "",
        "confidence": "",
        "risks": [],
        "citation_coverage": 0,
        "escalate_to_human": False,
    }


@pytest.mark.asyncio
async def test_gateway_routes_through_configured_provider():
    gateway = LLMGateway(provider=MockLLMProvider())
    response = await gateway.generate(TaskClass.REASONING, [LLMMessage(role="user", content="test")])
    assert response.provider == "mock"


def test_no_agent_module_imports_vendor_sdk_directly():
    """Agents must go through LLMGateway, never `import anthropic` / `from openai import`."""
    import pathlib

    agents_dir = pathlib.Path(__file__).resolve().parents[2] / "app" / "agents"
    for path in agents_dir.rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        assert "import anthropic" not in src, f"{path} imports anthropic directly"
        assert "from openai import" not in src, f"{path} imports openai directly"

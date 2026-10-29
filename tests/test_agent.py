"""Tests for LangGraph agent interaction helpers and conversational memory."""

import asyncio
from types import SimpleNamespace
from typing import Any
import pytest

from agents.fraud_agent import ask, build_system_prompt, create_fraud_agent_graph
from config.settings import ConfigurationError, Settings


class FakeAgent:
    """Mock LangGraph CompiledStateGraph for testing ask() behavior."""

    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, Any], dict[str, Any]]] = []

    async def ainvoke(self, input_data: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((input_data, config))
        user_message = input_data["messages"][0].content
        return {
            "messages": [
                SimpleNamespace(content=f"Processed: {user_message}")
            ]
        }


class SlowFakeAgent:
    """Mock agent that simulates hanging operations."""

    async def ainvoke(self, input_data: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(2)
        return {"messages": [SimpleNamespace(content="Done")]}


class EmptyFakeAgent:
    """Mock agent returning empty messages."""

    async def ainvoke(self, input_data: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        return {"messages": []}


def test_ask_preserves_thread_id_across_turns() -> None:
    """Verify that ask() carries thread_id through configuration for conversational memory."""
    async def exercise() -> None:
        agent = FakeAgent()
        resp1 = await ask(agent, "How many alerts?", "thread-abc", timeout_seconds=5)
        resp2 = await ask(agent, "Who closed it?", "thread-abc", timeout_seconds=5)

        assert resp1 == "Processed: How many alerts?"
        assert resp2 == "Processed: Who closed it?"
        assert len(agent.calls) == 2
        assert agent.calls[0][1]["configurable"]["thread_id"] == "thread-abc"
        assert agent.calls[1][1]["configurable"]["thread_id"] == "thread-abc"

    asyncio.run(exercise())


def test_ask_handles_timeout() -> None:
    """Verify that ask() raises TimeoutError when the agent takes too long."""
    async def exercise() -> None:
        agent = SlowFakeAgent()
        with pytest.raises(TimeoutError, match="timed out"):
            await ask(agent, "Hello", "thread-123", timeout_seconds=1)

    asyncio.run(exercise())


def test_ask_handles_empty_response() -> None:
    """Verify that ask() raises RuntimeError when agent produces empty output."""
    async def exercise() -> None:
        agent = EmptyFakeAgent()
        with pytest.raises(RuntimeError, match="empty response"):
            await ask(agent, "Query", "thread-123", timeout_seconds=5)

    asyncio.run(exercise())


def test_build_system_prompt_replaces_placeholders() -> None:
    """Verify system prompt populates database and collection from settings."""
    settings = Settings(
        mongodb_mcp_server_path="/mock/path",
        mongodb_connection_string="mongodb://localhost:27017",
        mongodb_database="custom_bank",
        mongodb_collection="custom_alerts",
    )
    prompt = build_system_prompt(settings)
    assert "Database: custom_bank" in prompt
    assert "Collection: custom_alerts" in prompt
    assert "<DATABASE>" not in prompt
    assert "<COLLECTION>" not in prompt


def test_create_fraud_agent_graph_requires_api_key() -> None:
    """Verify agent graph creation requires Groq API key."""
    settings = Settings(
        mongodb_mcp_server_path="/mock/path",
        mongodb_connection_string="mongodb://localhost:27017",
        groq_api_key=None,
    )
    with pytest.raises(ConfigurationError, match="GROQ_API_KEY"):
        asyncio.run(create_fraud_agent_graph(settings))

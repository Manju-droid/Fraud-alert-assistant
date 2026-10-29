"""Tests for MongoDB MCP tool safeguards, parameter bounding, and interceptors."""

import asyncio
from typing import Any
import pytest
from langchain_mcp_adapters.interceptors import MCPToolCallRequest
from mcp.types import CallToolResult, TextContent

from clients.mcp_client import (
    MongoDBSafetyError,
    SafeToolInterceptor,
    _bound_count_arguments,
    _bound_find_arguments,
    _raise_for_tool_error,
)
from config.settings import Settings


def make_test_settings(
    max_result_rows: int = 50,
    mcp_timeout_seconds: int = 2,
    database: str = "bankdemo",
    collection: str = "fraud_alerts",
) -> Settings:
    """Create test Settings instance without loading .env."""
    return Settings(
        mongodb_mcp_server_path="/mock/path/index.js",
        mongodb_connection_string="mongodb://localhost:27017/bankdemo",
        mongodb_database=database,
        mongodb_collection=collection,
        mongodb_read_only=True,
        groq_api_key="mock_key",
        groq_model="openai/gpt-oss-120b",
        max_result_rows=max_result_rows,
        mcp_timeout_seconds=mcp_timeout_seconds,
        agent_timeout_seconds=60,
    )


def test_interceptor_rejects_unapproved_tools() -> None:
    """Ensure write or administrative tools raise MongoDBSafetyError."""
    settings = make_test_settings()
    interceptor = SafeToolInterceptor(settings)

    unapproved_tools = ["delete_one", "insert_one", "drop_collection", "create_index", "run_command"]

    for tool_name in unapproved_tools:
        request = MCPToolCallRequest(
            name=tool_name,
            args={"database": "bankdemo", "collection": "fraud_alerts"},
            server_name="mongodb",
        )

        async def dummy_handler(call: MCPToolCallRequest) -> CallToolResult:
            return CallToolResult(content=[TextContent(type="text", text="ok")])

        with pytest.raises(MongoDBSafetyError, match="not allowed"):
            asyncio.run(interceptor(request, dummy_handler))


def test_interceptor_bounds_find_limit() -> None:
    """Ensure requested limits exceeding max_result_rows are capped."""
    settings = make_test_settings(max_result_rows=25)
    interceptor = SafeToolInterceptor(settings)

    captured_call = None

    async def mock_handler(call: MCPToolCallRequest) -> CallToolResult:
        nonlocal captured_call
        captured_call = call
        return CallToolResult(content=[TextContent(type="text", text="results")])

    request = MCPToolCallRequest(
        name="find",
        args={
            "database": "bankdemo",
            "collection": "fraud_alerts",
            "limit": 500,
        },
        server_name="mongodb",
    )

    asyncio.run(interceptor(request, mock_handler))
    assert captured_call is not None
    assert captured_call.args["limit"] == 25
    assert captured_call.args["connectionId"] == "preconfigured"


def test_interceptor_defaults_database_and_collection() -> None:
    """Ensure missing database and collection in find/count are defaulted."""
    settings = make_test_settings(database="bankdemo", collection="fraud_alerts")
    interceptor = SafeToolInterceptor(settings)

    captured_find = None
    captured_count = None

    async def mock_handler(call: MCPToolCallRequest) -> CallToolResult:
        nonlocal captured_find, captured_count
        if call.name == "find":
            captured_find = call
        else:
            captured_count = call
        return CallToolResult(content=[TextContent(type="text", text="ok")])

    # Find without db/coll
    asyncio.run(
        interceptor(
            MCPToolCallRequest(name="find", args={"filter": {}}, server_name="mongodb"),
            mock_handler,
        )
    )
    assert captured_find is not None
    assert captured_find.args["database"] == "bankdemo"
    assert captured_find.args["collection"] == "fraud_alerts"
    assert captured_find.args["limit"] == 10

    # Count without db/coll
    asyncio.run(
        interceptor(
            MCPToolCallRequest(name="count", args={"query": {}}, server_name="mongodb"),
            mock_handler,
        )
    )
    assert captured_count is not None
    assert captured_count.args["database"] == "bankdemo"
    assert captured_count.args["collection"] == "fraud_alerts"


def test_interceptor_rejects_unauthorized_scope() -> None:
    """Ensure querying unauthorized databases or collections raises MongoDBSafetyError."""
    settings = make_test_settings(database="bankdemo", collection="fraud_alerts")
    interceptor = SafeToolInterceptor(settings)

    async def mock_handler(call: MCPToolCallRequest) -> CallToolResult:
        return CallToolResult(content=[TextContent(type="text", text="ok")])

    # Wrong database
    with pytest.raises(MongoDBSafetyError, match="Unauthorized database"):
        asyncio.run(
            interceptor(
                MCPToolCallRequest(
                    name="find",
                    args={"database": "admin", "collection": "fraud_alerts"},
                    server_name="mongodb",
                ),
                mock_handler,
            )
        )

    # Wrong collection
    with pytest.raises(MongoDBSafetyError, match="Unauthorized collection"):
        asyncio.run(
            interceptor(
                MCPToolCallRequest(
                    name="find",
                    args={"database": "bankdemo", "collection": "internal_credentials"},
                    server_name="mongodb",
                ),
                mock_handler,
            )
        )


def test_interceptor_handles_timeout() -> None:
    """Ensure slow operations raise TimeoutError when exceeding mcp_timeout_seconds."""
    settings = make_test_settings(mcp_timeout_seconds=1)
    interceptor = SafeToolInterceptor(settings)

    async def slow_handler(call: MCPToolCallRequest) -> CallToolResult:
        await asyncio.sleep(2)
        return CallToolResult(content=[TextContent(type="text", text="slow")])

    request = MCPToolCallRequest(
        name="count",
        args={"database": "bankdemo", "collection": "fraud_alerts"},
        server_name="mongodb",
    )

    with pytest.raises(TimeoutError, match="timed out"):
        asyncio.run(interceptor(request, slow_handler))


def test_raise_for_tool_error_detection() -> None:
    """Ensure tool error results are detected and raise RuntimeError."""
    error_res = CallToolResult(
        content=[TextContent(type="text", text="Unauthorized access")],
        isError=True,
    )
    with pytest.raises(RuntimeError, match="reported error"):
        _raise_for_tool_error(error_res)

    text_err_res = CallToolResult(
        content=[TextContent(type="text", text="error: collection not found")],
        isError=False,
    )
    with pytest.raises(RuntimeError, match="tool failed"):
        _raise_for_tool_error(text_err_res)

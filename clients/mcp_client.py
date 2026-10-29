"""MongoDB MCP connections and read-only tool safeguards."""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path for direct script execution
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from typing import TypeAlias
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from langchain_mcp_adapters.interceptors import (
    MCPToolCallRequest,
    ToolCallInterceptor,
)
from mcp.types import CallToolResult
MCPResult: TypeAlias = CallToolResult | ToolMessage | Command

from config.settings import Settings

logger = logging.getLogger("fraud_alert.mcp")

READ_ONLY_MONGODB_TOOLS = frozenset({"find", "count"})


class MongoDBSafetyError(ValueError):
    """Raised when a MongoDB operation violates safety or authorization boundaries."""


class MCPConnectionError(RuntimeError):
    """Raised when the MCP server fails to start, connect, or complete an operation."""


def _bound_find_arguments(
    request: MCPToolCallRequest,
    settings: Settings,
) -> MCPToolCallRequest:
    """Validate database scope and bound result limit for 'find' tool."""
    args = dict(request.args)

    # Enforce connectionId
    if not args.get("connectionId"):
        args["connectionId"] = "preconfigured"

    # Validate database scope
    db = args.get("database")
    if not db:
        args["database"] = settings.mongodb_database
    elif db != settings.mongodb_database:
        raise MongoDBSafetyError(
            f"Unauthorized database '{db}'. Only '{settings.mongodb_database}' is allowed."
        )

    # Validate collection scope
    coll = args.get("collection")
    if not coll:
        args["collection"] = settings.mongodb_collection
    elif coll != settings.mongodb_collection:
        raise MongoDBSafetyError(
            f"Unauthorized collection '{coll}'. Only '{settings.mongodb_collection}' is allowed."
        )

    # Bound limit
    if "limit" in args:
        requested_limit = args["limit"]
        if isinstance(requested_limit, bool) or not isinstance(requested_limit, int):
            raise MongoDBSafetyError("The result limit must be an integer.")
        args["limit"] = min(max(requested_limit, 1), settings.max_result_rows)
    else:
        args["limit"] = min(10, settings.max_result_rows)

    return request.override(args=args)


def _bound_count_arguments(
    request: MCPToolCallRequest,
    settings: Settings,
) -> MCPToolCallRequest:
    """Validate database and collection scope for 'count' tool."""
    args = dict(request.args)

    # Enforce connectionId
    if not args.get("connectionId"):
        args["connectionId"] = "preconfigured"

    # Validate database scope
    db = args.get("database")
    if not db:
        args["database"] = settings.mongodb_database
    elif db != settings.mongodb_database:
        raise MongoDBSafetyError(
            f"Unauthorized database '{db}'. Only '{settings.mongodb_database}' is allowed."
        )

    # Validate collection scope
    coll = args.get("collection")
    if not coll:
        args["collection"] = settings.mongodb_collection
    elif coll != settings.mongodb_collection:
        raise MongoDBSafetyError(
            f"Unauthorized collection '{coll}'. Only '{settings.mongodb_collection}' is allowed."
        )

    return request.override(args=args)


def _raise_for_tool_error(result: MCPResult) -> None:
    """Check tool result for error flags or failure messages."""
    if not isinstance(result, CallToolResult):
        return
    if getattr(result, "isError", False):
        error_msg = ""
        for content in result.content:
            text = getattr(content, "text", "")
            if text:
                error_msg += f" {text}"
        raise RuntimeError(f"MongoDB MCP tool reported error:{error_msg}")

    for content in result.content:
        text = getattr(content, "text", None)
        if isinstance(text, str) and text.lstrip().lower().startswith("error:"):
            raise RuntimeError(f"MongoDB MCP tool failed: {text.strip()}")


class SafeToolInterceptor:
    """Interceptor that enforces read-only access, database scoping, and timeouts."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def __call__(
        self,
        request: MCPToolCallRequest,
        handler: Callable[[MCPToolCallRequest], Awaitable[MCPResult]],
    ) -> MCPResult:
        if "mongodb" in request.server_name.lower():
            if request.name not in READ_ONLY_MONGODB_TOOLS:
                raise MongoDBSafetyError(
                    f"MongoDB tool '{request.name}' is not allowed. "
                    f"Only read-only tools {sorted(READ_ONLY_MONGODB_TOOLS)} are permitted."
                )
            if request.name == "find":
                request = _bound_find_arguments(request, self.settings)
            elif request.name == "count":
                request = _bound_count_arguments(request, self.settings)

        try:
            result = await asyncio.wait_for(
                handler(request),
                timeout=self.settings.mcp_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            logger.error("MongoDB tool call timed out after %ds", self.settings.mcp_timeout_seconds)
            raise TimeoutError(
                f"MongoDB operation timed out after {self.settings.mcp_timeout_seconds} seconds."
            ) from exc

        _raise_for_tool_error(result)
        return result


def _tool_interceptor(settings: Settings) -> ToolCallInterceptor:
    """Create a ToolCallInterceptor instance."""
    return SafeToolInterceptor(settings)


def get_mcp_client(settings: Settings | None = None) -> MultiServerMCPClient:
    """Create a configured MultiServerMCPClient instance."""
    resolved_settings = settings or Settings.from_env()
    return MultiServerMCPClient(
        resolved_settings.mcp_servers,
        tool_interceptors=[_tool_interceptor(resolved_settings)],
        handle_tool_errors=False,
    )


async def get_mcp_tools(settings: Settings | None = None) -> list[BaseTool]:
    """Discover approved read-only tools from the MongoDB MCP Server."""
    resolved_settings = settings or Settings.from_env()
    client = get_mcp_client(resolved_settings)

    try:
        all_tools = await asyncio.wait_for(
            client.get_tools(server_name="mongodb"),
            timeout=resolved_settings.mcp_timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        raise MCPConnectionError(
            f"Timed out after {resolved_settings.mcp_timeout_seconds}s discovering MCP tools."
        ) from exc
    except Exception as exc:
        raise MCPConnectionError(
            f"Failed to connect to MongoDB MCP Server at {resolved_settings.mongodb_mcp_server_path}: {exc}"
        ) from exc

    # Filter to approved read-only tools
    filtered_tools = [
        tool for tool in all_tools if tool.name in READ_ONLY_MONGODB_TOOLS
    ]

    if not filtered_tools:
        raise MCPConnectionError(
            f"No approved read-only tools found on MongoDB MCP Server. Available: {[t.name for t in all_tools]}"
        )

    logger.debug("Discovered %d approved MCP tools: %s", len(filtered_tools), [t.name for t in filtered_tools])
    return filtered_tools


async def main() -> None:
    """CLI diagnostics for verifying MongoDB MCP tool discovery."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    settings = Settings.from_env()

    print("=" * 60)
    print("MongoDB MCP Client Diagnostics")
    print("=" * 60)
    print(f"Server Entrypoint: {settings.mongodb_mcp_server_path}")
    print(f"Target Database:   {settings.mongodb_database}")
    print(f"Target Collection: {settings.mongodb_collection}")
    print(f"Read-Only Mode:    {settings.mongodb_read_only}")
    print("\nConnecting to MongoDB MCP Server...")

    try:
        tools = await get_mcp_tools(settings)
        print(f"Successfully discovered {len(tools)} approved tools:\n")
        for tool in tools:
            print(f" - Tool: {tool.name}")
            print(f"   Description: {tool.description.strip() if tool.description else 'No description'}")
        print("\nAll health checks passed.")
    except Exception as exc:
        print(f"\nConnection failed: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    asyncio.run(main())

"""Live integration tests against the configured MongoDB MCP server and MongoDB instance."""

import asyncio
import json
import pytest

from clients.mcp_client import MongoDBSafetyError, get_mcp_tools
from config.settings import Settings

pytestmark = pytest.mark.integration


def test_mongodb_mcp_tool_discovery_and_live_queries() -> None:
    """Exercise live MCP server startup, tool discovery, and read queries."""
    async def exercise() -> None:
        settings = Settings.from_env()
        tools = await get_mcp_tools(settings)
        tool_map = {tool.name: tool for tool in tools}

        # Verify required read-only tools are discovered
        assert "find" in tool_map
        assert "count" in tool_map

        # Test count query against live MongoDB
        count_tool = tool_map["count"]
        count_res = await count_tool.ainvoke({
            "connectionId": "preconfigured",
            "database": settings.mongodb_database,
            "collection": settings.mongodb_collection,
            "query": {},
        })
        # Parse count result
        count_str = str(count_res)
        assert "150" in count_str

        # Test find query against specific alert
        find_tool = tool_map["find"]
        find_res = await find_tool.ainvoke({
            "connectionId": "preconfigured",
            "database": settings.mongodb_database,
            "collection": settings.mongodb_collection,
            "filter": {"alert_id": "ALT-1003"},
            "limit": 1,
        })
        find_str = str(find_res)
        assert "ALT-1003" in find_str

        # Test unauthorized database attempt raises MongoDBSafetyError
        with pytest.raises(MongoDBSafetyError, match="Unauthorized database"):
            await find_tool.ainvoke({
                "connectionId": "preconfigured",
                "database": "admin",
                "collection": settings.mongodb_collection,
                "filter": {},
            })

    asyncio.run(exercise())

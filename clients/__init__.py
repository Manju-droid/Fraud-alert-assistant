"""MCP clients and tool safeguards for Fraud Alert Assistant."""

import sys

from clients.mcp_client import (
    MCPConnectionError,
    MongoDBSafetyError,
    READ_ONLY_MONGODB_TOOLS,
    get_mcp_client,
    get_mcp_tools,
)

# Provide compatibility for legacy uppercase 'Clients' imports
sys.modules.setdefault("Clients", sys.modules[__name__])

__all__ = [
    "MCPConnectionError",
    "MongoDBSafetyError",
    "READ_ONLY_MONGODB_TOOLS",
    "get_mcp_client",
    "get_mcp_tools",
]

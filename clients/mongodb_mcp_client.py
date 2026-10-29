"""Backward-compatibility module for uppercase 'Clients' package path."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from clients.mcp_client import (
    MCPConnectionError,
    MongoDBSafetyError,
    READ_ONLY_MONGODB_TOOLS,
    get_mcp_client,
    get_mcp_tools,
    main,
)

__all__ = [
    "MCPConnectionError",
    "MongoDBSafetyError",
    "READ_ONLY_MONGODB_TOOLS",
    "get_mcp_client",
    "get_mcp_tools",
    "main",
]

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

import os
import asyncio
from pathlib import Path

from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient


# Step 1: Load environment variables
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


# Step 2: Path to locally built MongoDB MCP Server (optional override from .env)
mcp_server_env = os.getenv("MONGODB_MCP_SERVER_PATH")
SERVER_PATH = Path(mcp_server_env).expanduser().resolve() if mcp_server_env else None


# Step 3: Configure MCP client
def get_mcp_client() -> MultiServerMCPClient:

    mongodb_uri = (
        os.getenv("MDB_MCP_CONNECTION_STRING")
        or os.getenv("MONGODB_URI")
    )

    if not mongodb_uri:
        raise ValueError(
            "MongoDB connection string is missing in .env"
        )

    # If local path exists, use node directly; otherwise fall back to npx
    if SERVER_PATH and SERVER_PATH.is_file():
        server_command = "node"
        server_args = [str(SERVER_PATH), "--transport", "stdio"]
    else:
        server_command = "npx"
        server_args = ["-y", "mongodb-mcp-server@3.1.0", "--transport", "stdio"]

    read_only = os.getenv("MDB_MCP_READ_ONLY", "true").lower() in ("true", "1", "yes")

    client = MultiServerMCPClient({
        "mongodb": {
            "transport": "stdio",
            "command": server_command,
            "args": server_args,
            "env": {
                **os.environ,
                "MDB_MCP_CONNECTION_STRING": mongodb_uri,
                "MDB_MCP_READ_ONLY": "true" if read_only else "false"
            }
        }
    })

    return client


# Step 4: Discover available MCP tools
async def get_mcp_tools():

    client = get_mcp_client()

    tools = await client.get_tools(
        server_name="mongodb"
    )

    return tools


# Step 5: Test MCP tool discovery
async def main():

    print("Connecting to MongoDB MCP Server...")

    tools = await get_mcp_tools()

    print("\nMCP connection initialized.")
    print(f"Available tools: {len(tools)}\n")

    for tool in tools:
        print(f"Tool: {tool.name}")
        print(f"Description: {tool.description}")
        print("-" * 50)


if __name__ == "__main__":
    asyncio.run(main())

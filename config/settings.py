"""Environment-backed application settings and MCP configuration for Fraud Alert Assistant."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from langchain_mcp_adapters.sessions import Connection

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ConfigurationError(ValueError):
    """Raised when environment variables or application configuration are invalid."""


def sanitize_uri(uri: str | None) -> str:
    """Mask credentials in database URIs for safe logging and repr display."""
    if not uri:
        return ""
    return re.sub(r":([^@/]+)@", ":***@", uri)


def _resolve_mongodb_mcp_server_path(env_path: str | None) -> str:
    """Resolve the path to the compiled official MongoDB MCP Server entry point."""
    if env_path:
        candidate = Path(env_path).expanduser().resolve()
        if candidate.is_file():
            return str(candidate)
        if candidate.is_dir():
            nested_candidate = (
                candidate
                / "packages"
                / "mongodb-mcp-server"
                / "dist"
                / "esm"
                / "index.js"
            )
            if nested_candidate.is_file():
                return str(nested_candidate)
            dist_candidate = candidate / "dist" / "esm" / "index.js"
            if dist_candidate.is_file():
                return str(dist_candidate)
        raise ConfigurationError(
            f"Configured MONGODB_MCP_SERVER_PATH '{env_path}' does not exist."
        )

    # Search standard candidate locations on local developer machines
    candidate_locations = [
        Path.home()
        / "Downloads"
        / "mongodb-mcp-server-main"
        / "packages"
        / "mongodb-mcp-server"
        / "dist"
        / "esm"
        / "index.js",
        Path.home()
        / "Documents"
        / "mongodb-mcp-server-main"
        / "packages"
        / "mongodb-mcp-server"
        / "dist"
        / "esm"
        / "index.js",
        Path.home()
        / "Downloads"
        / "mongodb-mcp-server"
        / "packages"
        / "mongodb-mcp-server"
        / "dist"
        / "esm"
        / "index.js",
        PROJECT_ROOT
        / "mongodb-mcp-server"
        / "packages"
        / "mongodb-mcp-server"
        / "dist"
        / "esm"
        / "index.js",
        PROJECT_ROOT.parent
        / "mongodb-mcp-server-main"
        / "packages"
        / "mongodb-mcp-server"
        / "dist"
        / "esm"
        / "index.js",
    ]

    for candidate in candidate_locations:
        if candidate.is_file():
            return str(candidate)

    raise ConfigurationError(
        "Could not find the compiled MongoDB MCP server entry point "
        "(packages/mongodb-mcp-server/dist/esm/index.js). "
        "Set MONGODB_MCP_SERVER_PATH in .env to point to the built index.js file."
    )


@dataclass(frozen=True)
class Settings:
    """Application configuration for MongoDB MCP and LangGraph agent."""

    mongodb_mcp_server_path: str
    mongodb_connection_string: str
    mongodb_database: str = "bankdemo"
    mongodb_collection: str = "fraud_alerts"
    mongodb_read_only: bool = True
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"
    max_result_rows: int = 50
    mcp_timeout_seconds: int = 30
    agent_timeout_seconds: int = 120
    debug: bool = False

    def __repr__(self) -> str:
        masked_uri = sanitize_uri(self.mongodb_connection_string)
        masked_key = "***" if self.groq_api_key else None
        return (
            f"Settings(server_path={self.mongodb_mcp_server_path!r}, "
            f"mongodb_uri={masked_uri!r}, db={self.mongodb_database!r}, "
            f"collection={self.mongodb_collection!r}, read_only={self.mongodb_read_only}, "
            f"groq_api_key={masked_key!r}, groq_model={self.groq_model!r}, "
            f"max_rows={self.max_result_rows}, mcp_timeout={self.mcp_timeout_seconds}s, "
            f"agent_timeout={self.agent_timeout_seconds}s, debug={self.debug})"
        )

    @classmethod
    def from_env(
        cls,
        env_file: Path | str | None = None,
        load_env: bool = True,
    ) -> Settings:
        """Load settings from environment variables and optionally .env."""
        if load_env:
            if env_file:
                load_dotenv(Path(env_file).expanduser().resolve(), override=True)
            else:
                load_dotenv(PROJECT_ROOT / ".env", override=False)

        # Parse numeric parameters
        try:
            max_result_rows = int(os.getenv("MAX_RESULT_ROWS", "50"))
            mcp_timeout_seconds = int(os.getenv("MCP_TIMEOUT_SECONDS", "30"))
            agent_timeout_seconds = int(os.getenv("AGENT_TIMEOUT_SECONDS", "120"))
        except ValueError as exc:
            raise ConfigurationError(
                "MAX_RESULT_ROWS, MCP_TIMEOUT_SECONDS, and AGENT_TIMEOUT_SECONDS must be integers."
            ) from exc

        if not 1 <= max_result_rows <= 500:
            raise ConfigurationError("MAX_RESULT_ROWS must be between 1 and 500.")
        if mcp_timeout_seconds < 1:
            raise ConfigurationError("MCP_TIMEOUT_SECONDS must be at least 1.")
        if agent_timeout_seconds < 1:
            raise ConfigurationError("AGENT_TIMEOUT_SECONDS must be at least 1.")

        # Database and collection
        mongodb_database = os.getenv("MONGODB_DATABASE") or os.getenv("MONGODB_DB") or "bankdemo"
        mongodb_collection = os.getenv("MONGODB_COLLECTION") or "fraud_alerts"

        # Connection string
        connection_string = (
            os.getenv("MDB_MCP_CONNECTION_STRING")
            or os.getenv("MONGODB_URI")
            or os.getenv("mongodb_uri")
        )
        if not connection_string:
            raise ConfigurationError(
                "MDB_MCP_CONNECTION_STRING (or MONGODB_URI) is required in .env."
            )

        # Read only flag
        read_only_val = os.getenv("MDB_MCP_READ_ONLY", "true").lower()
        mongodb_read_only = read_only_val in ("true", "1", "yes")

        # MCP Server path
        server_path_env = os.getenv("MONGODB_MCP_SERVER_PATH")
        server_path = _resolve_mongodb_mcp_server_path(server_path_env)

        # Groq settings
        groq_api_key = os.getenv("GROQ_API_KEY") or os.getenv("api_key") or None
        groq_model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

        # Debug mode
        debug = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")

        return cls(
            mongodb_mcp_server_path=server_path,
            mongodb_connection_string=connection_string,
            mongodb_database=mongodb_database,
            mongodb_collection=mongodb_collection,
            mongodb_read_only=mongodb_read_only,
            groq_api_key=groq_api_key,
            groq_model=groq_model,
            max_result_rows=max_result_rows,
            mcp_timeout_seconds=mcp_timeout_seconds,
            agent_timeout_seconds=agent_timeout_seconds,
            debug=debug,
        )

    @property
    def mcp_servers(self) -> dict[str, Connection]:
        """Return MCP server configuration dictionary for MultiServerMCPClient."""
        sanitized_env = {
            **os.environ,
            "MDB_MCP_CONNECTION_STRING": self.mongodb_connection_string,
            "MDB_MCP_READ_ONLY": "true" if self.mongodb_read_only else "false",
        }
        return {
            "mongodb": {
                "transport": "stdio",
                "command": "node",
                "args": [self.mongodb_mcp_server_path, "--transport", "stdio"],
                "env": sanitized_env,
            }
        }

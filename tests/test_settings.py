"""Tests for environment-backed configuration and validation."""

from pathlib import Path
import pytest

from config.settings import ConfigurationError, Settings, sanitize_uri


def test_settings_configure_mongodb_stdio_transport() -> None:
    """Validate MCP connection dictionary conforms to MultiServerMCPClient stdio format."""
    settings = Settings(
        mongodb_mcp_server_path="/path/to/dist/esm/index.js",
        mongodb_connection_string="mongodb://localhost:27017/bankdemo",
        mongodb_database="bankdemo",
        mongodb_collection="fraud_alerts",
        mongodb_read_only=True,
        groq_api_key="mock_key",
        groq_model="openai/gpt-oss-120b",
        max_result_rows=50,
        mcp_timeout_seconds=30,
        agent_timeout_seconds=120,
    )

    config = settings.mcp_servers
    assert "mongodb" in config
    assert config["mongodb"]["transport"] == "stdio"
    assert config["mongodb"]["command"] == "node"
    assert config["mongodb"]["args"] == ["/path/to/dist/esm/index.js", "--transport", "stdio"]
    env = config["mongodb"].get("env") or {}
    assert env.get("MDB_MCP_CONNECTION_STRING") == "mongodb://localhost:27017/bankdemo"
    assert env.get("MDB_MCP_READ_ONLY") == "true"


def test_sanitize_uri_masks_passwords() -> None:
    """Ensure credentials in MongoDB connection strings are masked."""
    sample_user = "test_analyst"
    sample_pass = "mock_password_to_mask"
    raw = f"mongodb://{sample_user}:{sample_pass}@10.0.1.5:27017/bankdemo?authSource=admin"
    sanitized = sanitize_uri(raw)
    assert sample_pass not in sanitized
    assert f"{sample_user}:***@10.0.1.5:27017" in sanitized


def test_settings_repr_never_leaks_secrets() -> None:
    """Ensure repr(Settings) does not output raw passwords or API keys."""
    mock_pwd = "mock_secret_password_123"
    mock_key = "mock_groq_api_key_456"
    settings = Settings(
        mongodb_mcp_server_path="/path/to/index.js",
        mongodb_connection_string=f"mongodb://user:{mock_pwd}@localhost:27017/bankdemo",
        groq_api_key=mock_key,
    )
    text = repr(settings)
    assert mock_pwd not in text
    assert mock_key not in text
    assert "***" in text


def test_settings_validation_invalid_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure invalid integer bounds raise ConfigurationError."""
    monkeypatch.setenv("MAX_RESULT_ROWS", "0")
    monkeypatch.setenv("MDB_MCP_CONNECTION_STRING", "mongodb://127.0.0.1:27017")
    monkeypatch.setenv("MONGODB_MCP_SERVER_PATH", str(Path(__file__).resolve()))

    with pytest.raises(ConfigurationError, match="MAX_RESULT_ROWS"):
        Settings.from_env(load_env=False)


def test_settings_validation_missing_connection_string(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure missing connection string raises ConfigurationError."""
    monkeypatch.delenv("MDB_MCP_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("MONGODB_URI", raising=False)
    monkeypatch.delenv("mongodb_uri", raising=False)
    monkeypatch.setenv("MONGODB_MCP_SERVER_PATH", str(Path(__file__).resolve()))

    with pytest.raises(ConfigurationError, match="MDB_MCP_CONNECTION_STRING"):
        Settings.from_env(load_env=False)


def test_settings_server_path_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure nonexistent MCP server path raises ConfigurationError."""
    monkeypatch.setenv("MONGODB_MCP_SERVER_PATH", "/non/existent/path/index.js")
    monkeypatch.setenv("MDB_MCP_CONNECTION_STRING", "mongodb://127.0.0.1:27017")

    with pytest.raises(ConfigurationError, match="Configured MONGODB_MCP_SERVER_PATH"):
        Settings.from_env(load_env=False)

"""Tests for MongoDB safety rules and argument validation."""

import pytest
from langchain_mcp_adapters.interceptors import MCPToolCallRequest

from clients.mcp_client import (
    MongoDBSafetyError,
    _bound_count_arguments,
    _bound_find_arguments,
)
from config.settings import Settings


def make_settings() -> Settings:
    return Settings(
        mongodb_mcp_server_path="/dummy/path",
        mongodb_connection_string="mongodb://localhost:27017/bankdemo",
        mongodb_database="bankdemo",
        mongodb_collection="fraud_alerts",
        max_result_rows=50,
    )


def test_find_non_integer_limit_rejected() -> None:
    settings = make_settings()
    for bad_limit in ["10", True, False, 10.5, None]:
        if bad_limit is None:
            continue
        req = MCPToolCallRequest(
            name="find",
            args={"limit": bad_limit},
            server_name="mongodb",
        )
        with pytest.raises(MongoDBSafetyError, match="must be an integer"):
            _bound_find_arguments(req, settings)


def test_find_negative_limit_bounded_to_one() -> None:
    settings = make_settings()
    req = MCPToolCallRequest(
        name="find",
        args={"limit": -5},
        server_name="mongodb",
    )
    bounded = _bound_find_arguments(req, settings)
    assert bounded.args["limit"] == 1


def test_count_unauthorized_database_rejected() -> None:
    settings = make_settings()
    req = MCPToolCallRequest(
        name="count",
        args={"database": "malicious_db"},
        server_name="mongodb",
    )
    with pytest.raises(MongoDBSafetyError, match="Unauthorized database"):
        _bound_count_arguments(req, settings)


def test_count_unauthorized_collection_rejected() -> None:
    settings = make_settings()
    req = MCPToolCallRequest(
        name="count",
        args={"collection": "passwords"},
        server_name="mongodb",
    )
    with pytest.raises(MongoDBSafetyError, match="Unauthorized collection"):
        _bound_count_arguments(req, settings)

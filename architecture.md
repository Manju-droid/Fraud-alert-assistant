# Fraud Alert Assistant Architecture

## Overview
Fraud Alert Assistant processes and analyzes bank fraud alerts using a conversational LLM agent, MongoDB storage, and the official Model Context Protocol (MCP) server.

## Components
- **Database Engine**: MongoDB Community Server (`bankdemo.fraud_alerts`)
- **Seeding Script**: Data generation and index creation (`Scripts/seed.py`)
- **Agents**: LangGraph ReAct conversational agent (`agents/fraud_agent.py`)
- **MCP Client**: MultiServerMCPClient integration (`Clients/mongodb_mcp_client.py`)
- **MCP Server**: Official MongoDB MCP Server (`@mongodb-js/mongodb-mcp-server`) communicating via `stdio`

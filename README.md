# Banking Fraud Alert Assistant - Enterprise Setup & Deployment Guide

A conversational AI assistant designed for financial fraud triage and investigation analysis, powered by **LangGraph**, **Groq LLM** (`openai/gpt-oss-120b`), and the official **MongoDB Model Context Protocol (MCP) Server** communicating over `stdio`.

The assistant allows fraud operations teams and analysts to query, inspect, and summarize fraud alert records using natural conversational English. It handles complex queries, executes read-only MongoDB operations, and preserves multi-turn conversation memory for seamless follow-up investigations.

---

## Table of Contents

1. [Project Overview & Architecture](#1-project-overview--architecture)
2. [Prerequisites & Compatibility](#2-prerequisites--compatibility)
3. [Check Existing Installations](#3-check-existing-installations)
4. [Step-by-Step Installation & Setup](#4-step-by-step-installation--setup)
   - [Step 1: Clone the Application Repository](#step-1-clone-the-application-repository)
   - [Step 2: Clone the Official MongoDB MCP Server](#step-2-clone-the-official-mongodb-mcp-server)
   - [Step 3: Build the Official MongoDB MCP Server](#step-3-build-the-official-mongodb-mcp-server)
   - [Step 4: Create Python 3.12 Virtual Environment](#step-4-create-python-312-virtual-environment)
   - [Step 5: Install Python Dependencies](#step-5-install-python-dependencies)
   - [Step 6: Configure Environment Variables](#step-6-configure-environment-variables)
5. [Environment Variables Reference](#5-environment-variables-reference)
6. [MCP Server & Client Architecture](#6-mcp-server--client-architecture)
7. [Verify MCP Tool Discovery & Connectivity](#7-verify-mcp-tool-discovery--connectivity)
8. [Run the LangGraph Conversational Agent](#8-run-the-langgraph-conversational-agent)
9. [Automated Testing Suite](#9-automated-testing-suite)
10. [Troubleshooting Guide](#10-troubleshooting-guide)
11. [Security, Governance & Access Control](#11-security-governance--access-control)
12. [Production Deployment Checklist & Architecture Limitations](#12-production-deployment-checklist--architecture-limitations)
13. [Development Utilities (Optional Seed Script)](#13-development-utilities-optional-seed-script)
14. [Project Directory Structure](#14-project-directory-structure)

---

## 1. Project Overview & Architecture

### Purpose
In enterprise banking operations, fraud analysts need rapid, structured insights into alert backlogs, transaction anomalies, geographic velocities, and investigation outcomes. The Fraud Alert Assistant allows analysts to interact with MongoDB fraud alert collections through conversational dialogue—similar to ChatGPT—without requiring analysts to author manual aggregation pipelines or database queries.

### Architectural Workflow

```text
User Query (Terminal / Application Interface)
         │
         ▼
    [Agent Node] ◄────────────────────────────────────────────────────┐
 (Groq: openai/gpt-oss-120b)                                          │
         │                                                            │
         ▼ (tools_condition)                                          │
   Requires Database Query?                                           │
   ├── YES ──► [ToolNode]                                             │
   │                │                                                 │
   │                ▼                                                 │
   │         [SafeToolInterceptor]                                    │
   │         • Enforces Read-Only Whitelist (find, count)             │
   │         • Bounds Result Limits (1 <= limit <= MAX_RESULT_ROWS)   │
   │         • Validates Database & Collection Scope                  │
   │                │                                                 │
   │                ▼                                                 │
   │         [MultiServerMCPClient]                                   │
   │                │                                                 │
   │                ▼ (stdio transport: JSON-RPC)                     │
   │   [Official MongoDB MCP Server] (node index.js)                  │
   │                │                                                 │
   │                ▼ (MongoDB Wire Protocol / TLS)                   │
   │   [Enterprise MongoDB Cluster / Atlas / Server]                  │
   │                │                                                 │
   │                └─────────────────────────────────────────────────┘
   │
   └── NO ───► [Synthesized Conversational Answer]
                    │
                    ▼
          [MemorySaver Checkpointer] (Preserves thread context)
```

### Component Responsibilities

| Component | Technology | Primary Responsibility |
| :--- | :--- | :--- |
| **Conversational Agent** | LangGraph (`StateGraph`), LangChain Core | Orchestrates the ReAct reasoning loop, binds tools to the LLM, and formats user responses. |
| **Language Model** | Groq API (`openai/gpt-oss-120b`) | Generates structured tool calls based on user intent and synthesizes natural language answers. |
| **Conversation State** | LangGraph `MemorySaver` | Preserves multi-turn conversation history per `thread_id` so users can ask contextual follow-up questions. |
| **MCP Client Safeguards** | Python (`SafeToolInterceptor`) | Enforces read-only tool authorization, bounds query limits, and restricts database/collection scope. |
| **MCP Subprocess Manager** | `langchain-mcp-adapters` (`MultiServerMCPClient`) | Manages the child process lifecycle, standard input/output (`stdio`) transport, and timeouts. |
| **Official MCP Server** | `@mongodb-js/mongodb-mcp-server` (Node.js) | Official server developed by MongoDB; converts MCP tool requests into MongoDB driver queries. |
| **Database Tier** | MongoDB (Self-hosted, Enterprise, or Atlas) | High-performance document store housing banking fraud alerts and audit trails. |

---

## 2. Prerequisites & Compatibility

Before starting the setup, ensure your environment meets the minimum version requirements:

| Component | Minimum Version | Recommended Version | Purpose |
| :--- | :--- | :--- | :--- |
| **Python** | `3.12.0` | `3.12.x` | Required for LangGraph agent and MCP client libraries. |
| **Node.js** | `18.0.0` (LTS) | `20.x` or `22.x` (LTS) | Required to build and execute the official MongoDB MCP server. |
| **Corepack & pnpm** | `pnpm 8.0.0` | `pnpm 9.x` | Package manager required to build the MongoDB MCP server repository. |
| **Git** | `2.30.0` | Latest | For repository cloning and version control. |
| **MongoDB** | `5.0.0` | `6.0+` or MongoDB Atlas | Company database storing fraud alert records (self-hosted or cloud). |
| **Groq API Key** | N/A | Active Account | LLM inference provider for reasoning and tool invocation. |

> [!NOTE]
> You **do not** need to install MongoDB locally if your organization already hosts a shared MongoDB development, staging, or Atlas cluster. The assistant connects over network URIs using standard authentication and TLS.

---

## 3. Check Existing Installations

Run the following commands in your terminal to verify whether required software is already present on your machine:

```bash
# Check Python version
python3.12 --version || python3 --version

# Check Node.js and npm versions
node --version
npm --version

# Check Corepack and pnpm versions
corepack --version
pnpm --version

# Check Git
git --version
```

### Interpreting the Results
- **Python:** Must output `Python 3.12.x`. If it displays Python 3.10 or 3.11, install Python 3.12.
- **Node.js:** Must output `v18.x.x`, `v20.x.x`, or higher.
- **pnpm:** If `command not found: pnpm`, enable it using `corepack enable` (bundled with Node.js).
- **MongoDB:** To test connectivity to an existing MongoDB server, you can optionally check `mongosh --version`.

---

## 4. Step-by-Step Installation & Setup

Follow these steps sequentially to set up and launch the application.

### Step 1: Clone the Application Repository
Clone this repository to your preferred local workspace:

```bash
git clone <COMPANY_REPO_URL>/fraud-alert-assistant.git
cd fraud-alert-assistant
```

---

### Step 2: Clone the Official MongoDB MCP Server
The MongoDB MCP Server is an official open-source project by MongoDB (`@mongodb-js/mongodb-mcp-server`) that is maintained in a separate repository.

Clone the official repository into a separate sibling directory:

```bash
# Move to parent folder
cd ..

# Clone the official MongoDB MCP server repository
git clone https://github.com/mongodb-js/mongodb-mcp-server.git
cd mongodb-mcp-server
```

---

### Step 3: Build the Official MongoDB MCP Server
The official MongoDB MCP server is a TypeScript monorepo built using `pnpm`.

```bash
# Enable corepack if pnpm is not available
corepack enable

# Install server dependencies
pnpm install

# Compile TypeScript packages into JavaScript
pnpm run build
```

#### Identify the Compiled Entry Point
After the build completes, verify that the compiled ESM entry point exists:

```bash
ls -l packages/mongodb-mcp-server/dist/esm/index.js
```

Note the absolute path to this file (e.g., `/Users/<username>/workspace/mongodb-mcp-server/packages/mongodb-mcp-server/dist/esm/index.js` or `/home/<username>/mongodb-mcp-server/packages/mongodb-mcp-server/dist/esm/index.js`). You will reference this path in your `.env` file.

---

### Step 4: Create Python 3.12 Virtual Environment
Return to the `fraud-alert-assistant` application directory and create an isolated Python 3.12 virtual environment:

```bash
# Return to the application directory
cd ../fraud-alert-assistant

# Create virtual environment using Python 3.12
python3.12 -m venv .venv

# Activate the virtual environment:
# On macOS / Linux:
source .venv/bin/activate
```

Verify your active Python path:
```bash
which python
python --version
# Output must point to .venv and show Python 3.12.x
```

---

### Step 5: Install Python Dependencies
Install the required application dependencies, LangGraph packages, MCP adapters, and test suite:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

### Step 6: Configure Environment Variables
Copy the template configuration file to `.env`:

```bash
cp .env.example .env
```

Open `.env` in your editor and configure your environment settings. See the next section for full variable definitions.

---

## 5. Environment Variables Reference

All application settings are managed through environment variables loaded via `config/settings.py`.

### Configuration Options

| Variable Name | Required | Default Value | Description |
| :--- | :---: | :--- | :--- |
| `MDB_MCP_CONNECTION_STRING` | **Yes** | None | Full MongoDB connection URI passed to the MCP server child process. Supports standard URIs and Atlas SRV records with authentication, replica sets, and TLS. |
| `MDB_MCP_READ_ONLY` | No | `"true"` | Enforces read-only mode in the official MongoDB MCP server. When enabled, only read operations (`find`, `count`, etc.) are exposed. |
| `MONGODB_MCP_SERVER_PATH` | No | Auto-discovered | Path to the compiled official MongoDB MCP Server entry point (`packages/mongodb-mcp-server/dist/esm/index.js`). If unset, searches standard paths in `Downloads`, `Documents`, or workspace root. |
| `MONGODB_URI` | No | None | Fallback connection URI if `MDB_MCP_CONNECTION_STRING` is not explicitly set. |
| `MONGODB_DATABASE` | No | `"bankdemo"` | Target database name where fraud alert collections reside. |
| `MONGODB_COLLECTION` | No | `"fraud_alerts"` | Target collection name containing fraud alert documents. |
| `GROQ_API_KEY` | **Yes** | None | API key from Groq Console used for agent LLM tool calling. |
| `GROQ_MODEL` | No | `"openai/gpt-oss-120b"` | Groq LLM model used for reasoning and tool orchestration. |
| `MAX_RESULT_ROWS` | No | `50` | Maximum number of documents returned by a single `find` query (bounded between `1` and `500`). |
| `MCP_TIMEOUT_SECONDS` | No | `30` | Subprocess timeout in seconds for executing an MCP tool call. |
| `AGENT_TIMEOUT_SECONDS` | No | `120` | End-to-end timeout in seconds for agent reasoning and response synthesis. |
| `DEBUG` | No | `"false"` | When set to `"true"`, outputs internal tool selection and argument diagnostics in the terminal. |

---

### Safe Production `.env` Template

Create your `.env` file using the template below:

```bash
# ==============================================================================
# Fraud Alert Assistant - Production Configuration Template
# ==============================================================================

# 1. Groq LLM Credentials (Required)
GROQ_API_KEY="<your_groq_api_key_here>"
GROQ_MODEL="openai/gpt-oss-120b"

# 2. Target Database & Collection Scope
MONGODB_DATABASE="fraud_operations"
MONGODB_COLLECTION="alerts"

# 3. MongoDB MCP Connection String
# Example 1: Enterprise Internal MongoDB with TLS and authentication:
MDB_MCP_CONNECTION_STRING="mongodb://<username>:<password>@mongo-cluster.internal.corp:27017/fraud_operations?authSource=admin&ssl=true"

# Example 2: MongoDB Atlas Cloud Cluster:
# MDB_MCP_CONNECTION_STRING="mongodb+srv://<username>:<password>@prod-cluster.mongodb.net/fraud_operations?retryWrites=true&w=majority"

# Enforce strict read-only access (Recommended: true)
MDB_MCP_READ_ONLY="true"

# 4. Path to Compiled MongoDB MCP Server
MONGODB_MCP_SERVER_PATH="/absolute/path/to/mongodb-mcp-server/packages/mongodb-mcp-server/dist/esm/index.js"

# 5. Operational Bounds & Timeouts
MAX_RESULT_ROWS="50"
MCP_TIMEOUT_SECONDS="30"
AGENT_TIMEOUT_SECONDS="120"
DEBUG="false"
```

> [!CAUTION]
> Never commit your `.env` file or store raw production database passwords in source control. Ensure `.env` is listed in `.gitignore`.

---

## 6. MCP Server & Client Architecture

Understanding how the Python client and Node.js MCP server communicate is critical for troubleshooting and operational monitoring:

1. **Separate Build Artifact:** The official MongoDB MCP server (`@mongodb-js/mongodb-mcp-server`) is a TypeScript application that must be cloned and compiled separately using Node.js and pnpm.
2. **Process-Level Integration (stdio):** The Python client uses `langchain-mcp-adapters` with the standard input/output (`stdio`) transport.
3. **No Separate Server Daemon Needed:** When you initialize the client or start the agent, the Python application **automatically spawns the Node.js process** (`node <MONGODB_MCP_SERVER_PATH> --transport stdio`). You do **not** need to run a separate background service or web server for MCP.
4. **Environment Isolation:** Database credentials and the read-only flag are passed directly to the spawned child process through environment variables (`MDB_MCP_CONNECTION_STRING`, `MDB_MCP_READ_ONLY`).
5. **Client-Level Safeguards:** The Python client intercepts all tool executions through `SafeToolInterceptor`:
   - Enforces tool whitelisting (`find` and `count` only).
   - Validates that queries only access the configured `MONGODB_DATABASE` and `MONGODB_COLLECTION`.
   - Bounds the query `limit` parameter to prevent accidental memory exhaustion or huge result payloads.

---

## 7. Verify MCP Tool Discovery & Connectivity

Before running the conversational agent, run the standalone client diagnostic script to test your connection string, Node.js process launch, and tool discovery:

```bash
# Ensure virtual environment is active
source .venv/bin/activate

# Execute MCP client diagnostics
python clients/mcp_client.py
```

### Expected Success Output

```text
============================================================
MongoDB MCP Client Diagnostics
============================================================
Server Entrypoint: /path/to/mongodb-mcp-server/packages/mongodb-mcp-server/dist/esm/index.js
Target Database:   fraud_operations
Target Collection: alerts
Read-Only Mode:    True

Connecting to MongoDB MCP Server...
Successfully discovered 2 approved tools:

 - Tool: count
   Description: Gets the number of documents in a MongoDB collection using db.collection.count() and query as an optional filter parameter
 - Tool: find
   Description: Run a find query against a MongoDB collection

All health checks passed.
```

If the diagnostic command succeeds, your environment is ready to start the agent.

---

## 8. Run the LangGraph Conversational Agent

Launch the interactive conversational fraud assistant from the repository root:

```bash
python -m agents.fraud_agent
```

### Session Startup Banner

```text
Connecting to Banking Fraud Alert Assistant...
Assistant ready! Multi-turn conversational memory active.

============================================================
       BANKING FRAUD ALERT ASSISTANT
============================================================
Ask any question regarding fraud alerts, risks, or analyst outcomes.
Commands: 'exit' / 'quit' to terminate, 'debug on/off' to toggle tool logs.

You:
```

### Supported Interactive Commands

- `exit` or `quit`: Safely terminates the session and frees resources.
- `debug on`: Toggles verbose logging, displaying tool calls, query filters, and execution statuses.
- `debug off`: Returns to clean, professional conversational output.

### Example Queries

#### 1. Metric / Count Query
> **You:** `How many high risk alerts are currently open?`  
> **Assistant:** `There are currently 14 high-risk alerts in Open status awaiting analyst review.`

#### 2. Detailed Ticket Summary
> **You:** `Summarize alert ALT-8921.`  
> **Assistant:**  
> **Alert ALT-8921 – Executive Summary**  
> - **Pattern:** Unusual Overseas Transaction Spike  
> - **Risk Level:** High (Risk Score: 84.0)  
> - **Transaction Details:** EUR 4,850.00 at Airline Ticket Office from Rome, Italy  
> - **Customer:** CUST-49102  
> - **Status:** Under Review (Assigned to analyst.chen@bank.com)

#### 3. Multi-Turn Follow-Up (Conversational Memory)
> **You:** `Who investigated it?`  
> **Assistant:** `Alert ALT-8921 was investigated by analyst.chen@bank.com.` *(The agent remembers the context without re-asking for the ticket ID).*

---

## 9. Automated Testing Suite

The repository includes a comprehensive `pytest` test suite covering configuration validation, argument bounding, scope protection, conversational memory, and live MCP integration.

### Run Unit Tests (Mocked / Offline)
To run the standard unit tests without requiring a live MongoDB connection:

```bash
pytest
```

**Expected Output:**
```text
============================= test session starts ==============================
collected 22 items / 1 deselected / 21 selected

tests/test_agent.py .....                                                [ 23%]
tests/test_mcp_client.py ......                                          [ 52%]
tests/test_safety.py ....                                                [ 71%]
tests/test_settings.py ......                                            [100%]

======================= 21 passed, 1 deselected in 2.43s =======================
```

### Run Live Integration Tests
To execute integration tests against your configured live MongoDB server and compiled MCP server:

```bash
pytest -m "not integration or integration"
```

### Test Suite Structure

| Test File | Focus Area |
| :--- | :--- |
| [tests/test_settings.py](tests/test_settings.py) | Validates environment variable parsing, bounds enforcement, URI credential masking, and server path resolution. |
| [tests/test_mcp_client.py](tests/test_mcp_client.py) | Tests `SafeToolInterceptor`, ensuring write tools are rejected, `limit` arguments are bounded, and timeouts trigger cleanly. |
| [tests/test_safety.py](tests/test_safety.py) | Tests edge cases: non-integer limits, negative limits, and unauthorized database/collection scope rejections. |
| [tests/test_agent.py](tests/test_agent.py) | Tests LangGraph `ask()` helper, multi-turn memory preservation across turns, and timeout handling. |
| [tests/test_mongodb_mcp.py](tests/test_mongodb_mcp.py) | Live integration test verifying tool discovery, `count`, and `find` queries against the real database. |

---

## 10. Troubleshooting Guide

| Issue / Error Message | Root Cause | Resolution |
| :--- | :--- | :--- |
| `ConfigurationError: Could not find the compiled MongoDB MCP server entry point` | `MONGODB_MCP_SERVER_PATH` is incorrect, or the TypeScript build was not run. | 1. Ensure you cloned the MongoDB MCP server.<br>2. Run `pnpm run build` inside the server repo.<br>3. Verify the file `packages/mongodb-mcp-server/dist/esm/index.js` exists.<br>4. Set `MONGODB_MCP_SERVER_PATH` in `.env` to the absolute path of `index.js`. |
| `ConfigurationError: MDB_MCP_CONNECTION_STRING ... is required` | `.env` was not created or connection URI is missing. | Copy `.env.example` to `.env` and configure `MDB_MCP_CONNECTION_STRING`. |
| `ConfigurationError: GROQ_API_KEY is not configured in .env` | `GROQ_API_KEY` is missing or empty. | Obtain an API key from [Groq Console](https://console.groq.com) and set it in `.env`. |
| `MCPConnectionError: Failed to connect to MongoDB MCP Server` | Node.js is missing from your system path or Node version is incompatible. | Ensure `node --version` outputs v18+ or v20+ and Node is executable in your terminal. |
| `MongoDBSafetyError: Unauthorized database ...` | The LLM attempted to query a database outside your configured `MONGODB_DATABASE`. | By design, `SafeToolInterceptor` blocks cross-database access. If your data lives in another database, update `MONGODB_DATABASE` in `.env`. |
| `MongoDBSafetyError: The result limit must be an integer` | A query passed a non-integer limit. | The client automatically bounds integer limits. Verify custom queries or increase `MAX_RESULT_ROWS` in `.env`. |
| `TimeoutError: Agent timed out after 120 seconds` | The Groq API or MongoDB query took longer than the configured timeout. | Increase `AGENT_TIMEOUT_SECONDS` or `MCP_TIMEOUT_SECONDS` in `.env`. Check MongoDB network latency. |
| `ServerSelectionTimeoutError` / Connection Refused | MongoDB cluster is unreachable or firewall blocks port 27017. | 1. Verify MongoDB network access.<br>2. For Atlas, verify your IP is whitelisted in Network Access.<br>3. For corporate clusters, ensure VPN is connected. |

---

## 11. Security, Governance & Access Control

### 1. Multi-Tiered Read-Only Enforcement
Production security requires defense in depth:
- **Database Role:** The MongoDB user configured in `MDB_MCP_CONNECTION_STRING` should be granted **strictly read-only roles** (e.g., `read` role on the specific database). Never configure a `readWrite` or `dbAdmin` credential.
- **Server Flag:** The official MCP server subprocess is launched with `MDB_MCP_READ_ONLY="true"`.
- **Client Interceptor:** Python's `SafeToolInterceptor` intercepts all tool calls and enforces `READ_ONLY_MONGODB_TOOLS = frozenset({"find", "count"})`. Any write, update, drop, or administration command is immediately rejected before execution.

### 2. Database & Collection Scoping
To prevent accidental access to other collections or system databases:
- The interceptor enforces that `database == settings.mongodb_database` and `collection == settings.mongodb_collection`.
- Attempts to query `admin`, `config`, `local`, or other corporate collections trigger a `MongoDBSafetyError`.

### 3. Credential Protection
- Connection strings and API keys are strictly loaded from environment variables.
- `Settings.__repr__()` implements automatic URI sanitization, replacing database passwords (`mongodb://user:***@host`) and masking Groq API keys with `***` to prevent accidental leakage in logs or stack traces.

### 4. Enterprise LLM Data Privacy
- Records retrieved from MongoDB are passed into the Groq LLM context window to generate natural language summaries.
- Before deploying to production, ensure your organization has executed an enterprise agreement with Groq covering data residency, HIPAA/SOC2 compliance, and **Zero Data Retention (ZDR)** to ensure customer records are not stored or used for model training.

---

## 12. Production Deployment Checklist & Architecture Limitations

Before deploying this application to a production enterprise environment, review the following architecture limitations and deployment requirements:

### Architecture Limitations

1. **Ephemeral In-Memory Conversation State:**
   - **Current State:** The application uses LangGraph `MemorySaver`, which stores conversation checkpoints in local process memory (RAM).
   - **Production Requirement:** For multi-container or distributed cloud deployments (e.g., Kubernetes, Amazon ECS, Google Cloud Run), replace `MemorySaver` with a persistent external checkpointer, such as `langgraph-checkpoint-postgres` or Redis, so sessions persist across container restarts and scale across replicas.

2. **Interface Protocol (CLI vs. API):**
   - **Current State:** The entry point is an interactive terminal CLI (`python -m agents.fraud_agent`).
   - **Production Requirement:** Wrap the agent graph (`create_fraud_agent_graph()`) in a REST or WebSocket service using **FastAPI** to integrate with enterprise fraud case management systems.

3. **Subprocess stdio Scaling:**
   - **Current State:** The client uses `stdio` to spawn a dedicated Node.js MCP server process per Python agent process.
   - **Production Requirement:** For high-concurrency microservice architectures, deploy the MongoDB MCP server as a standalone HTTP/SSE service and configure the Python client with HTTP/SSE transports.

4. **Telemetry & Audit Logging:**
   - **Current State:** Logging is directed to standard output with debug toggle.
   - **Production Requirement:** Integrate structured JSON logging and distributed tracing (e.g., OpenTelemetry, Datadog, or LangSmith) to audit every database query and user prompt for compliance.

---

## 13. Development Utilities (Optional Seed Script)

The repository contains an optional developer utility at `Scripts/seed.py`.

> [!CAUTION]
> **DO NOT EXECUTE `Scripts/seed.py` IN PRODUCTION.**  
> The script contains `collection.delete_many({})`, which will **permanently erase existing data** in the target collection. It is strictly intended for isolated local development sandboxes.

If you are developing locally in an empty sandbox environment and wish to generate synthetic test records:

```bash
# ONLY run this against an isolated local test database:
python Scripts/seed.py
```

---

## 14. Project Directory Structure

```text
fraud-alert-assistant/
├── .env.example                  # Environment configuration template (Safe to commit)
├── requirements.txt               # Application dependencies and test framework
├── pytest.ini                     # Pytest runner configuration (asyncio mode, markers)
├── pyrightconfig.json             # Python 3.12 typing configuration (0 errors)
├── architecture.md                # Component architecture notes
├── README.md                      # Production setup and operational documentation
├── config/
│   ├── __init__.py                # Package exports
│   └── settings.py                # Centralized environment parsing, bounds & server resolution
├── clients/
│   ├── __init__.py                # Package exports & legacy module compatibility alias
│   ├── mcp_client.py              # MultiServerMCPClient, SafeToolInterceptor & parameter bounding
│   └── mongodb_mcp_client.py      # Backward-compatible client wrapper
├── agents/
│   ├── __init__.py                # Package exports
│   └── fraud_agent.py             # LangGraph StateGraph ReAct agent, MemorySaver & prompt
├── tests/
│   ├── __init__.py                # Test package marker
│   ├── test_settings.py           # Configuration parsing & secret masking tests
│   ├── test_mcp_client.py         # Interceptor, timeout & tool boundary tests
│   ├── test_safety.py             # Database/collection scope validation tests
│   ├── test_agent.py              # Agent conversational memory & timeout tests
│   └── test_mongodb_mcp.py        # Live integration test against MongoDB MCP Server
└── Scripts/
    └── seed.py                    # [DEV ONLY] Sandbox database seeder (Never run in prod)
```

---

## License & Support

Maintained by the Financial Crime & Operations Engineering Team. For questions or deployment assistance, open an internal ticket or reach out to the project maintainers.

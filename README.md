# Banking Fraud Alert Assistant

A conversational AI assistant designed for financial fraud triage, powered by **LangGraph**, **Groq LLM** (`openai/gpt-oss-120b`), and the official **MongoDB Model Context Protocol (MCP) Server** communicating via `stdio`.

The assistant understands natural language queries, automatically determines when to query MongoDB, dynamically invokes official MongoDB MCP tools (`find`, `count`), and provides professional, context-aware answers with multi-turn conversation memory.

---

## Table of Contents

1. [Project Overview & Architecture](#1-project-overview--architecture)
2. [Prerequisites](#2-prerequisites)
3. [Check Existing Installations FIRST](#3-check-existing-installations-first)
4. [Install Missing Prerequisites](#4-install-missing-prerequisites)
5. [Clone the Fraud Alert Assistant Repository](#5-clone-the-fraud-alert-assistant-repository)
6. [Set Up MongoDB Locally](#6-set-up-mongodb-locally)
7. [Seed the MongoDB Database](#7-seed-the-mongodb-database)
8. [MongoDB MCP Server Prerequisite](#8-mongodb-mcp-server-prerequisite)
9. [Create Python Virtual Environment](#9-create-python-virtual-environment)
10. [Install Python Dependencies](#10-install-python-dependencies)
11. [Configure Environment Variables](#11-configure-environment-variables)
12. [Verify MongoDB and MCP Client Connection](#12-verify-mongodb-and-mcp-client-connection)
13. [Run the LangGraph Agent](#13-run-the-langgraph-agent)
14. [Example Questions & Conversational Flow](#14-example-questions--conversational-flow)
15. [Troubleshooting Guide](#15-troubleshooting-guide)
16. [Project Structure](#16-project-structure)
17. [Security & Governance](#17-security--governance)

---

## 1. Project Overview & Architecture

### Purpose
In modern banking operations, fraud analysts need quick, accurate insights into alert backlogs, transaction anomalies, geographic velocities, and investigation histories. The Fraud Alert Assistant allows analysts to query and triage MongoDB fraud alert records using conversational English—similar to ChatGPT—without writing manual MongoDB aggregation pipelines or database queries.

### Architecture Workflow

```text
User Question (Interactive Terminal)
         │
         ▼
    [Agent Node] ◄────────────────────────────────────────┐
 (Groq: openai/gpt-oss-120b)                              │
         │                                                │
         ▼ (tools_condition)                              │
   Requires Tool Call?                                    │
   ├── YES ──► [ToolNode]                                 │
   │                │                                     │
   │                ▼                                     │
   │         [MCP Client] (MultiServerMCPClient)          │
   │                │                                     │
   │                ▼ (stdio transport)                   │
   │   [Official MongoDB MCP Server] (node index.js)      │
   │                │                                     │
   │                ▼                                     │
   │     [MongoDB Community Server] (bankdemo database)   │
   │                │                                     │
   │                └─────────────────────────────────────┘
   │
   └── NO ───► [Final Response] (Displayed to Analyst)
```

### Component Roles

| Component | Technology | Role |
|---|---|---|
| **Conversational Agent** | LangGraph `StateGraph` | Orchestrates the ReAct execution loop, manages conversation checkpointing (`MemorySaver`), and formats conversational responses. |
| **Language Model** | Groq (`openai/gpt-oss-120b`) | Interprets user intent, selects MCP tools, generates MongoDB query criteria, and synthesizes natural-language answers. |
| **MCP Client** | `langchain-mcp-adapters` (`MultiServerMCPClient`) | Connects Python to the MCP Server over standard I/O (`stdio`), discovers tools dynamically, and executes queries. |
| **MCP Server** | `@mongodb-js/mongodb-mcp-server` | Official Model Context Protocol server exposing read-only MongoDB operations (`find`, `count`) to the agent. |
| **Database** | MongoDB Community Server (v6.0+) | Local database storing the `bankdemo.fraud_alerts` collection containing 150 synthetic banking fraud tickets. |

---

## 2. Prerequisites

The following software is required to run the Fraud Alert Assistant. Review compatible versions before proceeding:

| Software | Compatible Version | Purpose |
|---|---|---|
| **Python** | `3.12.x` | Application runtime and LangGraph agent execution. |
| **Node.js** | `v18.x`, `v20.x`, or `v22.x` (LTS) | Runtime required to execute the MongoDB MCP Server. |
| **Corepack & pnpm** | Corepack `0.34.0+`, pnpm `9.x` or `10.x` | Package manager required to build the MongoDB MCP Server from source. |
| **MongoDB Server** | Community Edition `6.0+`, `7.0+`, or `8.0+` | Database engine storing demo fraud records. |
| **MongoDB Shell** | `mongosh` `2.x+` | CLI utility to inspect and verify database records. |
| **MongoDB MCP Server** | Official GitHub repository | Model Context Protocol server built into local ESM bundle. |
| **Groq API Key** | Active account on [console.groq.com](https://console.groq.com) | LLM inference backend for the LangGraph agent. |

---

## 3. Check Existing Installations FIRST

Before downloading or installing any software, open your terminal and check which tools are already installed on your system.

Run the following commands:

```bash
python3.12 --version
node --version
npm --version
corepack --version
pnpm --version
mongod --version
mongosh --version
```

### How to Interpret the Output

* **Tool is installed:** You will see a version string (e.g., `Python 3.12.15`, `v22.12.0`, `db version v8.0.4`).  
  👉 **Action:** Compare the version against the [Prerequisites](#2-prerequisites) table. If it meets the requirement, **skip installing that tool**.
* **Tool is missing:** You will see an error such as `command not found: <tool>` or `zsh: command not found: <tool>`.  
  👉 **Action:** Proceed to [Section 4](#4-install-missing-prerequisites) and follow the installation instructions only for the missing tool.

---

## 4. Install Missing Prerequisites

Follow the instructions below **only for tools identified as missing or incompatible** in Section 3.

### macOS (Recommended: Homebrew)

#### 1. Homebrew (Package Manager)
If Homebrew is not installed, install it by running:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```
Verify:
```bash
brew --version
```

#### 2. Python 3.12
```bash
brew install python@3.12
```
Verify:
```bash
python3.12 --version
# Expected: Python 3.12.x
```

#### 3. Node.js & npm (v20+ LTS)
```bash
brew install node
```
Verify:
```bash
node --version
npm --version
```

#### 4. Corepack & pnpm
Node.js comes bundled with `corepack`. Enable it to use `pnpm`:
```bash
corepack enable
pnpm --version
```
*Alternative (if `corepack` is unavailable):*
```bash
npm install -g pnpm
pnpm --version
```

#### 5. MongoDB Community Server & mongosh
Tap the official MongoDB Homebrew repository and install:
```bash
brew tap mongodb/brew
brew install mongodb-community
brew install mongosh
```
Verify:
```bash
mongod --version | head -n 1
mongosh --version
```

---

### Linux (Ubuntu / Debian Guidance)

* **Python 3.12:**
  ```bash
  sudo apt update && sudo apt install -y python3.12 python3.12-venv python3.12-dev
  ```
* **Node.js (LTS via NodeSource):**
  ```bash
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo apt install -y nodejs
  sudo corepack enable
  ```
* **MongoDB Community Server:** Follow the official MongoDB Linux guide: [Install MongoDB Community Edition on Ubuntu](https://www.mongodb.com/docs/manual/tutorial/install-mongodb-on-ubuntu/).
* **MongoDB Shell (`mongosh`):** Follow [Install mongosh on Linux](https://www.mongodb.com/docs/mongodb-shell/install/).

---

## 5. Clone the Fraud Alert Assistant Repository

Clone the application repository to your local development machine. You can clone it into any workspace directory of your choice (e.g., `~/Documents` or `~/projects`):

```bash
# Navigate to your preferred workspace
cd ~/Documents

# Clone the company repository (replace placeholder with your actual Git URL)
git clone <COMPANY_REPOSITORY_URL>/Fraud-alert-assistant.git

# Enter the project directory
cd Fraud-alert-assistant
```

---

## 6. Set Up MongoDB Locally

The application connects to a local MongoDB instance running on port `27017`.

### Step 1: Start MongoDB Community Server

* **macOS (Homebrew):**
  ```bash
  brew services start mongodb-community
  ```
* **Linux (systemd):**
  ```bash
  sudo systemctl start mongod
  ```

### Step 2: Verify MongoDB is Running

* **macOS:**
  ```bash
  brew services list
  # Confirm "mongodb-community" displays status "started"
  ```
* **Linux:**
  ```bash
  sudo systemctl status mongod
  ```

### Step 3: Connect Using `mongosh`

Open the MongoDB shell to confirm port `27017` is accepting connections:

```bash
mongosh "mongodb://127.0.0.1:27017"
```

Inside the shell, verify the target database:

```javascript
// Switch to the project database
use bankdemo

// Check if collection exists and has documents
db.fraud_alerts.countDocuments()

// Exit the shell
exit
```

*Note:* If `countDocuments()` returns `0`, proceed directly to Section 7 to populate the initial records.

---

## 7. Seed the MongoDB Database

> [!CAUTION]
> **Data Deletion Warning:** Running `Scripts/seed.py` executes `collection.delete_many({})`. It will **wipe all existing records** in `bankdemo.fraud_alerts` before inserting fresh mock data. Do not run this script against a production database containing real customer data.

### Script Details (Verified from `Scripts/seed.py`)

* **Actual Path:** `Scripts/seed.py`
* **Purpose:** Generates a synthetic dataset of **exactly 150** banking fraud alerts with realistic transaction metadata, customer references, risk scores, rule triggers, analyst notes, and decision histories.
* **Database & Collection Populated:** `bankdemo.fraud_alerts`
* **Distribution of 150 Alerts:**
  * **90 False Positives (~60%):** Low/Medium risk alerts closed after customer contact.
  * **23 Confirmed Fraud (~15%):** High/Critical risk alerts with cards blocked and SAR review flags.
  * **37 Open Cases (~25%):** Unresolved alerts actively queued for secondary fraud triage.
* **Indexes Created Automatically:**
  * `alert_id` (Unique index)
  * `status` (Ascending)
  * `risk_score` (Ascending)
  * `customer_ref` (Ascending)
  * `created_at` (Ascending)
* **Idempotency:** Yes. Because it deletes existing records before re-inserting, you can run it multiple times without accumulating duplicates; the collection will always reset to 150 records.

### Prerequisites to Run `seed.py`

1. MongoDB must be running locally on `127.0.0.1:27017`.
2. Python virtual environment must be active with `pymongo` and `python-dotenv` installed (see [Sections 9 & 10](#9-create-python-virtual-environment)).

### Seeding Command

Run the seeder from the repository root:

```bash
# Ensure your virtual environment is active
source .venv/bin/activate

# Execute the seeder
python Scripts/seed.py
```

### Expected Terminal Output

```text
Connecting to MongoDB at mongodb://127.0.0.1:27017...

==================================================
MongoDB Seeding Summary
==================================================
Database:          bankdemo
Collection:        fraud_alerts
Inserted:          150
 - False Positive: 90 (60.0%)
 - Confirmed Fraud:23 (15.3%)
 - Open:           37 (24.7%)

Created Indexes:
 - _id_
 - alert_id_1
 - status_1
 - risk_score_1
 - customer_ref_1
 - created_at_1
==================================================
```

### Verify the Seeded Data in `mongosh`

```bash
mongosh "mongodb://127.0.0.1:27017/bankdemo" --eval "
  print('Total Alerts: ' + db.fraud_alerts.countDocuments());
  print('Sample Alert: ' + db.fraud_alerts.findOne({}, {alert_id: 1, risk_level: 1, status: 1}));
"
```

---

## 8. MongoDB MCP Server Prerequisite

The **official MongoDB MCP Server** is an open-source project maintained by MongoDB in a separate repository:
🔗 **[https://github.com/mongodb-js/mongodb-mcp-server](https://github.com/mongodb-js/mongodb-mcp-server)**

The MCP Server communicates with our Python client over standard I/O (`stdio`) using Node.js.

### Building the Official MCP Server from GitHub Source

You can clone the MCP server repository into **any folder outside of this project** (e.g., `~/Downloads` or `~/projects`):

```bash
# 1. Clone the official MongoDB MCP Server repository
cd ~/Downloads
git clone https://github.com/mongodb-js/mongodb-mcp-server.git
cd mongodb-mcp-server

# 2. Install dependencies using pnpm
pnpm install

# 3. Build the TypeScript source code into ESM JavaScript
pnpm run build
```

### Verify the Compiled Entry Point Exists

Confirm that the compiled JavaScript entry point was generated:

```bash
ls -la packages/mongodb-mcp-server/dist/esm/index.js
```

Copy the **absolute path** to this `index.js` file. For example:
```text
/Users/yourusername/Downloads/mongodb-mcp-server/packages/mongodb-mcp-server/dist/esm/index.js
```
You will paste this path into the fraud assistant's `.env` file in [Section 11](#11-configure-environment-variables).

> [!TIP]
> **Automatic `npx` Fallback:** If you do not wish to build the MCP server from source, leave `MONGODB_MCP_SERVER_PATH` blank in `.env`. The client in `Clients/mongodb_mcp_client.py` will automatically fall back to executing `npx -y mongodb-mcp-server@3.1.0`.

---

## 9. Create Python Virtual Environment

Navigate back to your `Fraud-alert-assistant` repository root:

```bash
cd ~/Documents/Fraud-alert-assistant
```

Create and activate a virtual environment named `.venv` using **Python 3.12**:

### macOS / Linux
```bash
# Create virtual environment using Python 3.12
python3.12 -m venv .venv

# Activate the virtual environment
source .venv/bin/activate
```

### Windows (PowerShell)
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### Why a Virtual Environment is Recommended
A virtual environment ensures your application runs with the exact pinned package versions specified in `requirements.txt`. It isolates the project from system Python packages and prevents macOS LibreSSL warnings and dependency conflicts.

---

## 10. Install Python Dependencies

With the virtual environment active, install the Python application dependencies:

```bash
# Ensure pip is up to date
python -m pip install --upgrade pip

# Install project dependencies
python -m pip install -r requirements.txt
```

> [!NOTE]
> Python dependencies (`langgraph`, `langchain-groq`, `pymongo`, etc.) are installed strictly inside `.venv`. They are completely independent of the Node.js/pnpm packages used by the separate MongoDB MCP server.

---

## 11. Configure Environment Variables

The application requires an environment file named `.env` in the project root. A safe template with placeholders is provided as `.env.example`.

### Step 1: Create `.env` from Template

```bash
cp .env.example .env
```

### Step 2: Configure Your Settings

Open `.env` in your code editor and provide your values:

```env
# ==============================================================================
# Fraud Alert Assistant - Environment Configuration
# ==============================================================================

# 1. Groq API Key (Required for LLM tool calling)
# Obtain your free API key from https://console.groq.com
GROQ_API_KEY="gsk_your_actual_groq_api_key_here"

# 2. Local MongoDB Database Settings
MONGODB_URI="mongodb://127.0.0.1:27017"
MONGODB_DATABASE="bankdemo"
MONGODB_COLLECTION="fraud_alerts"

# 3. Official MongoDB MCP Server Settings
# Connection URI passed to the MCP server subprocess
MDB_MCP_CONNECTION_STRING="mongodb://127.0.0.1:27017/bankdemo"

# Enforce read-only safety (prevents database writes/deletions)
MDB_MCP_READ_ONLY="true"

# 4. Path to Compiled MongoDB MCP Server (From Section 8)
# IMPORTANT: Must point to the compiled 'index.js' file, NOT the repository root folder!
MONGODB_MCP_SERVER_PATH="/absolute/path/to/mongodb-mcp-server/packages/mongodb-mcp-server/dist/esm/index.js"

# 5. Optional Debug Mode (Set to "true" to display raw tool calls and parameters)
DEBUG="false"
```

> [!WARNING]
> Never commit `.env` to Git. It contains private API credentials. The file is already listed in `.gitignore`.

---

## 12. Verify MongoDB and MCP Client Connection

Before launching the full agent, verify that your local MongoDB database, seeded records, and MCP tool discovery are working properly.

Run the standalone client test:

```bash
# Must be executed from the project root with .venv active
python Clients/mongodb_mcp_client.py
```

*(Note: Ensure folder capitalization is preserved: `Clients/mongodb_mcp_client.py`)*

### Expected Successful Output

```text
Connecting to MongoDB MCP Server...

MCP connection initialized.
Available tools: 18

Tool: aggregate-db
Tool: aggregate
Tool: collection-indexes
Tool: collection-schema
Tool: collection-storage-size
Tool: connect
Tool: count
Tool: db-stats
Tool: disconnect
Tool: explain
Tool: export
Tool: find
Tool: list-collections
Tool: list-connections
Tool: list-databases
Tool: mongodb-logs
Tool: search-knowledge
Tool: list-knowledge-sources
--------------------------------------------------
```

---

## 13. Run the LangGraph Agent

Launch the interactive conversational fraud assistant from the repository root:

```bash
python -m agents.fraud_agent
```

### How the MCP Subprocess Works
When you execute `fraud_agent.py`, the Python `MultiServerMCPClient` automatically spawns the compiled Node.js MongoDB MCP server as a subprocess over standard input/output (`stdio`). **You do not need to run a separate terminal command or background daemon for the MCP server.**

### Session Startup Banner

```text
Connecting to Fraud Intelligence Assistant...
Assistant ready! Conversation memory active.

=======================================================
       BANKING FRAUD ALERT ASSISTANT
=======================================================
Ask any question about fraud alerts.
Type 'exit' to stop, or 'debug on/off' to toggle tool logs.

You: 
```

---

## 14. Example Questions & Conversational Flow

The assistant uses **LangGraph `MemorySaver`** to maintain conversational memory across the entire terminal session. You can ask initial questions and follow up naturally without repeating ticket IDs.

### 1. Direct Counts & Status Checks
```text
You: How many total fraud alerts are in the database?
Assistant: There are 150 fraud alert cases in the system.

You: How many of those are located in Canada?
Assistant: There are 28 fraud alerts involving transactions located in Canada.
```

### 2. Multi-Ticket Query (Table Output)
```text
You: Show me the top 3 highest risk alerts.
Assistant:
Here are the top 3 alerts with the highest risk scores:

| Alert ID | Alert Type | Risk Score | Risk Level | Status | Transaction |
|---|---|---|---|---|---|
| ALT-1087 | ATM_SUSPICIOUS_PIN_RETRIES | 99.3 | CRITICAL | Confirmed Fraud | $15,060.03 USD @ Walmart Supercenter (Tokyo) |
| ALT-1123 | GEO_VELOCITY_MISMATCH | 97.8 | CRITICAL | Confirmed Fraud | $5,459.06 USD @ Walmart Supercenter (Paris) |
| ALT-1027 | NEW_UNRECOGNIZED_DEVICE_LOGIN | 94.3 | CRITICAL | Confirmed Fraud | £13,656.44 GBP @ Western Union (New York) |
```

### 3. Case Summary & Conversational Follow-Ups (Memory in Action)
```text
You: Summarize alert ALT-1003.
Assistant:
Alert Summary – ALT-1003 (ObjectId: 6ad77c4b3dfecbdd108a6b47)

- Pattern: Flagged for GEO VELOCITY MISMATCH (Medium Risk, Score 47.5).
- Transaction: $9,205.12 USD purchase at Amazon US from Toronto, Canada via Online channel.
- Customer: Reference CUST-78372.
- Outcome: Closed as False Positive. The analyst contacted the cardholder, who verified 
  the purchase as legitimate and consistent with their profile.

You: Who investigated it?
Assistant:
The alert was investigated by analyst Kowalski (analyst.kowalski@bankdemo.com).

You: What was the transaction amount?
Assistant:
The transaction amount was $9,205.12 USD.

You: Why was it closed?
Assistant:
It was closed as a False Positive because Analyst Kowalski contacted the customer directly, 
and the customer confirmed that the large Amazon purchase was legitimate.
```

### 4. Toggle Debugging On the Fly
* Type `debug on` to display raw tool names, arguments, and execution statuses.
* Type `debug off` to return to clean, conversational output.
* Type `exit` or press `Ctrl + C` to end the session cleanly.

---

## 15. Troubleshooting Guide

| Issue / Error Message | Likely Cause | Solution |
|---|---|---|
| `zsh: command not found: python` | Virtual environment is not active or Python is not mapped in your shell. | Run `source .venv/bin/activate` or use `python3 -m agents.fraud_agent`. |
| `ImportError: cannot import name 'create_agent' from 'langchain.agents'` | Old LangChain code or attempting to run with system Python 3.9. | The project uses LangGraph `StateGraph` in Python 3.12. Ensure `.venv` is activated. |
| `ModuleNotFoundError: No module named 'Clients'` | Incorrect folder casing or running from outside repository root. | Ensure you run from the project root (`Fraud-alert-assistant`) and preserve capital `C` in `Clients`. |
| `FileNotFoundError: MongoDB MCP Server not found: ...` | `MONGODB_MCP_SERVER_PATH` in `.env` is incorrect or points to a folder instead of `index.js`. | Verify the path points to `packages/mongodb-mcp-server/dist/esm/index.js`. If not building from source, leave the variable blank in `.env`. |
| `ServerSelectionTimeoutError: 127.0.0.1:27017: Connection refused` | Local MongoDB Community Server is not running. | Run `brew services start mongodb-community` (macOS) or `sudo systemctl start mongod` (Linux). |
| `ValueError: GROQ_API_KEY is missing from .env` | `.env` was not created or `GROQ_API_KEY` is empty. | Copy `.env.example` to `.env` and insert a valid API key from [Groq Console](https://console.groq.com). |
| `Command failed: pnpm run build` | Node.js version is older than v18 or pnpm is missing. | Verify `node --version` is v18+ LTS and run `corepack enable` before building the MCP server. |
| Zero alerts returned (`count: 0`) | MongoDB database was not seeded. | Run `python Scripts/seed.py` from the project root with `.venv` active. |
| `LibreSSL Warning: urllib3 v2 only supports OpenSSL 1.1.1+` | macOS default Python 3.9 is being invoked instead of Homebrew Python 3.12. | Check `which python` with `.venv` active. Ensure `.venv` was created with `python3.12 -m venv .venv`. |

---

## 16. Project Structure

The project layout follows a modular structure:

```text
Fraud-alert-assistant/
├── .env.example             # Configuration template with placeholder values (Safe to commit)
├── .gitignore                # Excludes secrets (.env), virtual environment (.venv/), and cache files
├── README.md                 # Complete setup, architectural, and operational documentation
├── architecture.md           # Architecture notes and component interactions
├── pyrightconfig.json        # Pyright typing configuration with relative paths
├── pyrefly.toml              # IDE linter configuration
├── requirements.txt          # Production application dependencies
├── agents/
│   ├── __init__.py
│   └── fraud_agent.py        # LangGraph StateGraph ReAct agent with MemorySaver & Groq LLM
├── Clients/
│   ├── __init__.py           # Python package marker
│   └── mongodb_mcp_client.py # MultiServerMCPClient configured for official MongoDB MCP Server
└── Scripts/
    └── seed.py               # Database seeder (creates 150 synthetic bank fraud alerts & indexes)
```

---

## 17. Security & Governance

1. **Read-Only Enforcement:**
   * The MCP server subprocess is strictly launched with `MDB_MCP_READ_ONLY="true"`.
   * The LangGraph agent restricts tool selection exclusively to read operations: `ALLOWED_TOOLS = {"find", "count"}`.
   * Write, update, drop, or delete operations cannot be executed through the agent.
2. **Credential Protection:**
   * API keys (`GROQ_API_KEY`) and database URIs are loaded exclusively from local `.env`.
   * `.env` is permanently excluded from Git via `.gitignore`.
3. **Synthetic Sample Data:**
   * All 150 alert records, customer IDs, analyst names, and notes generated by `Scripts/seed.py` are 100% synthetic mock data.
   * Never import real cardholder PII or production banking credentials into a local demo environment.
4. **Session Memory Scope:**
   * The conversational memory powered by LangGraph `MemorySaver` is stored **in-memory** in RAM for the duration of the process.
   * Conversation history is automatically cleared upon exiting the application (`exit` or terminal close) and is not persisted to disk.
5. **Deployment Context:**
   * The local `stdio` process architecture is designed for developer workstations, exploratory triage, and internal demo evaluations. It does not enforce multi-tenant enterprise authorization.

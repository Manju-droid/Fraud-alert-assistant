#!/usr/bin/env python3

"""
Fraud Alert Assistant
Conversational LangGraph StateGraph Agent + Groq LLM + Official MongoDB MCP Server

Architecture:
User Question -> Agent Node -> ToolNode (MCP Client) -> Agent Node -> Final Conversational Answer
State Checkpointing: MemorySaver provides multi-turn conversational memory for seamless follow-up queries.
"""

import os
import sys
import asyncio
import json
import uuid
import warnings
from pathlib import Path

# Suppress non-actionable deprecation warnings for cleaner CLI UX
warnings.filterwarnings("ignore")

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Handle case variation for Clients / clients package
try:
    import Clients as _Clients
    sys.modules.setdefault("clients", _Clients)
    import Clients.mongodb_mcp_client as _mcp_client
    sys.modules.setdefault("clients.mongodb_mcp_client", _mcp_client)
except ImportError:
    pass

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langgraph.graph import StateGraph, MessagesState, START
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver

try:
    from Clients.mongodb_mcp_client import get_mcp_tools
except ImportError:
    from Clients.mongodb_mcp_client import get_mcp_tools


# ----------------------------------------
# 1. Load environment variables
# ----------------------------------------

load_dotenv(PROJECT_ROOT / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY") or os.getenv("api_key")

if not GROQ_API_KEY:
    raise ValueError(
        "GROQ_API_KEY is missing from .env"
    )

DATABASE = os.getenv(
    "MONGODB_DATABASE", "bankdemo"
)

COLLECTION = os.getenv(
    "MONGODB_COLLECTION", "fraud_alerts"
)

DEBUG_MODE = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")


# ----------------------------------------
# 2. Approved MCP Tools
# ----------------------------------------

ALLOWED_TOOLS = {
    "find",
    "count"
}


# ----------------------------------------
# 3. Conversational System Prompt
# ----------------------------------------

SYSTEM_PROMPT = ("""
You are an expert, professional Banking Fraud Intelligence Assistant—communicating naturally, clearly, and concisely, like ChatGPT or a senior fraud operations colleague.

You retrieve live fraud alert records from MongoDB using tools provided by the official MongoDB MCP Server.

Database: <DATABASE>
Collection: <COLLECTION>
Connection ID: preconfigured
Access: Read-only

Available document fields include:
- _id (MongoDB ObjectId hex string, e.g. "6ad77c4b3dfecbdd108a6b47")
- alert_id (e.g. "ALT-1003")
- alert_type (e.g. "GEO_VELOCITY_MISMATCH", "UNUSUAL_TRANSACTION_SPIKE", "ATM_SUSPICIOUS_PIN_RETRIES")
- risk_score (0 - 100)
- risk_level (stored in uppercase: "LOW", "MEDIUM", "HIGH", "CRITICAL")
- status (e.g. "Open", "Under Review", "Confirmed Fraud", "Closed - False Positive", "False Positive")
- transaction_details: location, amount, currency, merchant, channel, ip_address
- customer_ref (e.g. "CUST-78372")
- assigned_analyst (email of the investigating analyst)
- created_at, sla_due
- notes (investigation notes, analyst observations)
- decision_history (array of lifecycle actions with timestamps, actors, and comments)

Communication & Response Guidelines:
1. Natural, Conversational Tone:
   - Speak in clean, professional English. Never dump raw database field names, JSON dictionaries, or unformatted schema dumps unless explicitly asked.
2. Context-Aware Response Sizing:
   - Simple / Direct questions (e.g., "total cases", "how many from Canada"): Give a short, direct answer in 1-2 friendly sentences. Do not use tables or bullet lists for simple single-number counts.
   - Alert Summaries (e.g., "summarize ticket X", "what happened with Y"): Provide an executive summary highlighting what happened, the fraud pattern/type, the key transaction details (amount, merchant, location), the risk score/level, and the investigation outcome (who handled it and why it was resolved or closed).
   - In-depth / Specific Questions: Use clean bullet points or short structured sections with bold labels.
   - Comparisons & Multi-ticket Listings: Use a clean Markdown table ONLY when listing or comparing multiple distinct alerts.
3. Multi-Turn Conversational Memory:
   - You have full conversation memory across the session. When the user asks follow-up questions like "Who investigated it?", "Why was it closed?", "What was the amount?", or "Are there any others like this?", refer to the ticket and context established in previous turns without asking the user to repeat the ID.
4. Tool Query Construction:
   - When querying by ticket ID (e.g. 24-character ObjectId like "6ad77c4b3dfecbdd108a6b47" or business ID like "ALT-1001"), use:
     {"$or": [{"_id": {"$oid": "<id>"}}, {"_id": "<id>"}, {"alert_id": "<id>"}]}
   - When searching by location or text, use case-insensitive regex:
     {"transaction_details.location": {"$regex": "<term>", "$options": "i"}}
   - When searching for high-risk tickets:
     {"risk_level": {"$in": ["HIGH", "CRITICAL"]}}
5. Grounded Accuracy:
   - Base all answers strictly on returned MongoDB data. Never invent ticket IDs, names, or transaction numbers.
   - If no matching documents exist, politely inform the user.
""").replace("<DATABASE>", DATABASE).replace("<COLLECTION>", COLLECTION)


# ----------------------------------------
# 4. LangGraph StateGraph Agent
# ----------------------------------------

class FraudAlertAgent:

    def __init__(self, thread_id: str | None = None, debug: bool = False):
        self.app = None
        self.tools = []
        self.system_message = SystemMessage(content=SYSTEM_PROMPT)
        self.thread_id = thread_id or f"session-{uuid.uuid4().hex[:8]}"
        self.debug = debug or DEBUG_MODE
        self.checkpointer = MemorySaver()

    async def initialize(self):

        print("\nConnecting to Fraud Intelligence Assistant...")

        # Load MCP tools from existing client
        all_tools = await get_mcp_tools()

        # Filter to allowed tools
        self.tools = [
            tool
            for tool in all_tools
            if tool.name in ALLOWED_TOOLS
        ]

        if not self.tools:
            raise RuntimeError(
                "No approved MCP tools available from server."
            )

        if self.debug:
            print("\n[DEBUG] Available MCP Tools:")
            for tool in self.tools:
                print(f" - {tool.name}")

        # Initialize Groq LLM
        llm = ChatGroq(
            model="openai/gpt-oss-120b",
            api_key=GROQ_API_KEY,
            temperature=0
        )

        # Bind MCP tools to LLM
        llm_with_tools = llm.bind_tools(self.tools)

        # Define Agent node
        async def call_model(state: MessagesState):
            messages = state["messages"]
            # Ensure system prompt is prepended to the context
            if not isinstance(messages[0], SystemMessage):
                messages = [self.system_message] + list(messages)
            response = await llm_with_tools.ainvoke(messages)
            return {"messages": [response]}

        # Define Tool node
        tool_node = ToolNode(self.tools)

        # Build StateGraph
        workflow = StateGraph(MessagesState) # type: ignore[bad-specialization]
        workflow.add_node("agent", call_model)
        workflow.add_node("tools", tool_node)

        # Workflow edges: ReAct loop
        workflow.add_edge(START, "agent")
        workflow.add_conditional_edges("agent", tools_condition)
        workflow.add_edge("tools", "agent")

        # Compile LangGraph workflow with conversation checkpointer (Memory)
        self.app = workflow.compile(checkpointer=self.checkpointer)

        print("Assistant ready! Conversation memory active.\n")

    # ------------------------------------
    # 5. Process user question
    # ------------------------------------

    async def ask(self, question: str) -> str:

        if self.app is None:
            raise RuntimeError(
                "Agent is not initialized."
            )

        # Use thread_id for conversation memory state
        config = {
            "configurable": {
                "thread_id": self.thread_id
            }
        }

        response = await self.app.ainvoke(
            {"messages": [HumanMessage(content=question)]},
            config=config
        )

        # Optional Debug logging (only active when debug=True or DEBUG=true in .env)
        if self.debug:
            for message in response["messages"]:
                tool_calls = getattr(message, "tool_calls", None)
                if tool_calls:
                    for call in tool_calls:
                        print(f"\n[DEBUG Tool Selected] {call['name']}")
                        args = call.get("args", {})
                        sanitized_args = {k: v for k, v in args.items() if k != "connectionId"}
                        print(
                            "[DEBUG Parameters]",
                            json.dumps(sanitized_args, indent=2, default=str)
                        )

                if isinstance(message, ToolMessage) or getattr(message, "type", "") == "tool":
                    status = "failure" if getattr(message, "status", None) == "error" else "success"
                    tool_name = getattr(message, "name", "tool")
                    print(f"[DEBUG Execution] {tool_name}: {status}")

        final_message = response["messages"][-1]
        return final_message.content


# ----------------------------------------
# 6. Interactive Terminal
# ----------------------------------------

async def main():

    agent = FraudAlertAgent()
    await agent.initialize()

    print("=" * 55)
    print("       BANKING FRAUD ALERT ASSISTANT")
    print("=" * 55)
    print("Ask any question about fraud alerts.")
    print("Type 'exit' to stop, or 'debug on/off' to toggle tool logs.\n")

    while True:
        try:
            question = (
                await asyncio.to_thread(
                    input,
                    "You: "
                )
            ).strip()

            if question.lower() in {"exit", "quit", "q"}:
                print("\nGoodbye!")
                break

            if not question:
                continue

            if question.lower() == "debug on":
                agent.debug = True
                print("[Debug mode enabled: tool calls and parameters will be displayed]\n")
                continue
            elif question.lower() == "debug off":
                agent.debug = False
                print("[Debug mode disabled: clean conversational output]\n")
                continue

            print("\nThinking...")
            answer = await agent.ask(question)

            print(f"\nAssistant:\n{answer}\n")

        except (KeyboardInterrupt, EOFError, asyncio.CancelledError):
            print("\nSession ended.")
            break
        except Exception as error:
            print(f"\nError: {error}\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nGoodbye!")

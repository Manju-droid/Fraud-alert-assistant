#!/usr/bin/env python3

"""
LangGraph Conversational Agent for Banking Fraud Intelligence.

Architecture:
User Question -> Agent Node (Groq LLM) -> ToolNode (MongoDB MCP) -> Agent Node -> Final Answer
Multi-turn conversational memory is checkpointed via MemorySaver.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import uuid
import warnings
from pathlib import Path
from typing import Any, Optional

# Suppress non-actionable warnings for clean CLI output
warnings.filterwarnings("ignore")

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from pydantic import SecretStr

from clients.mcp_client import (
    MCPConnectionError,
    get_mcp_tools,
)
from config.settings import ConfigurationError, Settings

logger = logging.getLogger("fraud_alert.agent")

SYSTEM_PROMPT_TEMPLATE = """\
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
"""


def build_system_prompt(settings: Settings) -> str:
    """Populate database and collection in system prompt template."""
    return (
        SYSTEM_PROMPT_TEMPLATE
        .replace("<DATABASE>", settings.mongodb_database)
        .replace("<COLLECTION>", settings.mongodb_collection)
    )


async def create_fraud_agent_graph(
    settings: Settings,
    checkpointer: Any = None,
) -> CompiledStateGraph:
    """Build and compile the LangGraph ReAct StateGraph for fraud alert triage."""
    if not settings.groq_api_key:
        raise ConfigurationError("GROQ_API_KEY is not configured in .env.")

    tools = await get_mcp_tools(settings)
    if not tools:
        raise MCPConnectionError("No approved read-only tools available from MongoDB MCP Server.")

    system_message = SystemMessage(content=build_system_prompt(settings))

    llm = ChatGroq(
        model=settings.groq_model,
        api_key=SecretStr(settings.groq_api_key),
        temperature=0,
    )
    llm_with_tools = llm.bind_tools(tools)

    async def call_model(state: MessagesState) -> dict[str, Any]:
        messages = state["messages"]
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [system_message] + list(messages)
        response = await llm_with_tools.ainvoke(messages)
        return {"messages": [response]}

    tool_node = ToolNode(tools)

    workflow = StateGraph(MessagesState)  # type: ignore[bad-specialization]
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", tool_node)

    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", tools_condition)
    workflow.add_edge("tools", "agent")

    active_checkpointer = checkpointer if checkpointer is not None else MemorySaver()
    return workflow.compile(checkpointer=active_checkpointer)


async def ask(
    agent: Any,
    question: str,
    thread_id: str,
    timeout_seconds: int = 120,
) -> str:
    """Invoke the agent with conversational memory state for the given thread_id."""
    config: RunnableConfig = {
        "configurable": {
            "thread_id": thread_id,
        }
    }

    try:
        response = await asyncio.wait_for(
            agent.ainvoke(
                {"messages": [HumanMessage(content=question)]},
                config=config,
            ),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        raise TimeoutError(
            f"Agent timed out after {timeout_seconds} seconds awaiting LLM or tool response."
        ) from exc

    messages = response.get("messages", [])
    if not messages:
        raise RuntimeError("Agent produced an empty response.")

    final_content: Any = messages[-1].content
    if isinstance(final_content, str):
        return final_content
    if isinstance(final_content, list):
        return "\n".join(
            block["text"]
            for block in final_content
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        )
    return str(final_content)


class FraudAlertAgent:
    """Object-oriented wrapper preserving backwards compatibility with existing callers."""

    def __init__(
        self,
        thread_id: Optional[str] = None,
        debug: bool = False,
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or Settings.from_env()
        self.thread_id = thread_id or f"session-{uuid.uuid4().hex[:8]}"
        self.debug = debug or self.settings.debug
        self.app: Optional[CompiledStateGraph] = None
        self.tools: list[Any] = []
        self.checkpointer = MemorySaver()

    async def initialize(self) -> None:
        """Initialize the LangGraph agent and establish MCP tool connections."""
        logger.info("Initializing Fraud Alert Agent...")
        self.app = await create_fraud_agent_graph(
            settings=self.settings,
            checkpointer=self.checkpointer,
        )
        self.tools = await get_mcp_tools(self.settings)

    async def ask(self, question: str) -> str:
        """Submit a query to the agent."""
        if self.app is None:
            raise RuntimeError("Agent is not initialized. Call 'await agent.initialize()' first.")

        # Invoke agent
        config: RunnableConfig = {
            "configurable": {
                "thread_id": self.thread_id,
            }
        }

        response = await asyncio.wait_for(
            self.app.ainvoke(
                {"messages": [HumanMessage(content=question)]},
                config=config,
            ),
            timeout=self.settings.agent_timeout_seconds,
        )

        if self.debug:
            for message in response.get("messages", []):
                tool_calls = getattr(message, "tool_calls", None)
                if tool_calls:
                    for call in tool_calls:
                        print(f"\n[DEBUG Tool Call] {call['name']}")
                        args = call.get("args", {})
                        sanitized_args = {k: v for k, v in args.items() if k != "connectionId"}
                        print("[DEBUG Args]", json.dumps(sanitized_args, indent=2, default=str))
                if isinstance(message, ToolMessage) or getattr(message, "type", "") == "tool":
                    status = "failure" if getattr(message, "status", None) == "error" else "success"
                    print(f"[DEBUG Result] {getattr(message, 'name', 'tool')}: {status}")

        final_message = response["messages"][-1]
        content: Any = final_message.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(
                block["text"]
                for block in content
                if isinstance(block, dict) and isinstance(block.get("text"), str)
            )
        return str(content)


async def run_chat() -> None:
    """Run interactive terminal chat loop."""
    settings = Settings.from_env()
    print("Connecting to Banking Fraud Alert Assistant...")

    agent = FraudAlertAgent(settings=settings)
    try:
        await agent.initialize()
    except Exception as exc:
        print(f"\nInitialization Error: Could not start agent: {exc}")
        raise SystemExit(1) from exc

    print("Assistant ready! Multi-turn conversational memory active.\n")
    print("=" * 60)
    print("       BANKING FRAUD ALERT ASSISTANT")
    print("=" * 60)
    print("Ask any question regarding fraud alerts, risks, or analyst outcomes.")
    print("Commands: 'exit' / 'quit' to terminate, 'debug on/off' to toggle tool logs.\n")

    while True:
        try:
            question = (await asyncio.to_thread(input, "You: ")).strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            return

        if question.lower() in {"exit", "quit", "q"}:
            print("\nGoodbye!")
            return
        if not question:
            continue

        if question.lower() == "debug on":
            agent.debug = True
            print("[Debug mode enabled: tool calls and parameters will be displayed]\n")
            continue
        if question.lower() == "debug off":
            agent.debug = False
            print("[Debug mode disabled: clean conversational output]\n")
            continue

        print("\nThinking...")
        try:
            answer = await agent.ask(question)
            print(f"\nAssistant:\n{answer}\n")
        except TimeoutError:
            print("\nAssistant: The request timed out. Please verify MCP server and Groq availability.\n")
        except Exception as exc:
            print(f"\nAssistant: I encountered an error fulfilling your request: {exc}\n")


def main() -> None:
    """Application CLI entry point."""
    try:
        asyncio.run(run_chat())
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()

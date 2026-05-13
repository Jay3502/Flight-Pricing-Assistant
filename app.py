import asyncio
from langgraph.graph import StateGraph, END
import state
from tool_loader import ToolLoader
from agents.planner_agent import PlannerAgent
from tool_executor import ToolExecutor
from state import FlightSearchState
from nodes import search_node, normalize_node, optimize_node, explain_node
from mcp.client.streamable_http import streamable_http_client
from contextlib import AsyncExitStack
from mcp.client.session import ClientSession
import datetime
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not os.getenv("GROQ_API_KEY"):
    raise EnvironmentError(
        "GROQ_API_KEY not found. Add it to your .env file."
    )
if not os.getenv("SERP_API_KEY"):
    raise EnvironmentError(
        "SERP_API_KEY not found. Add it to your .env file."
    )

class MCPClient:
    def __init__(self, server_url):
        self.server_url = server_url
        self.session = None
        self._exit_stack = AsyncExitStack()

    async def connect(self):
        try:
            streams = await self._exit_stack.enter_async_context(
                streamable_http_client(self.server_url)
            )
            read, write = streams[0], streams[1]
            self.session = ClientSession(read, write)
            await self._exit_stack.enter_async_context(self.session)
            await self.session.initialize()
            logger.info("MCP connected and initialized (HTTP)")
        except Exception as e:
            await self.close()
            raise e

    async def list_tools(self, tag_filter=None):
        if not self.session:
            raise RuntimeError("MCP session not connected")
        result = await self.session.list_tools()
        tools = result.tools
        if tag_filter:
            tools = [t for t in tools if tag_filter in getattr(t, "tags", [])]
        return tools

    async def call_tool(self, tool_name, arguments):
        return await self.session.call_tool(tool_name, arguments)

    async def close(self):
        await self._exit_stack.aclose()
        logger.info("MCP connection closed")


# ── GRAPH FACTORY ─────────────────────────────────────────────────────────────

def get_compiled_app(planner, executor):

    async def call_planner(state: FlightSearchState):
        plan = planner.run(state["user_query"])
        if not plan:
            return {"explanation": "I couldn't identify the route or date. Could you be more specific?"}

        today = datetime.date.today()

        for call in plan:
            # ✅ FIX: validate BOTH outbound_date and return_date, not just outbound
            for date_key in ("outbound_date", "return_date"):
                date_str = call["args"].get(date_key)
                if not date_str:
                    continue
                try:
                    target_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                    if target_date < today:
                        logger.warning("%s %s is in the past — bumping to today", date_key, date_str)
                        call["args"][date_key] = today.strftime("%Y-%m-%d")
                    elif (target_date - today).days > 365:
                        return {"explanation": "Airlines only allow bookings up to 365 days in advance."}
                except (ValueError, TypeError):
                    pass

        # ✅ FIX: extract return_date from the planner's tool call and store it
        # in state so nodes.py explain_node can build the correct booking URL.
        # Previously this was never stored — explain_node had no way to know
        # whether the search was one-way or round-trip.
        return_date = plan[0].get("args", {}).get("return_date") if plan else None

        logger.info(
            "Planner produced plan: %s | return_date=%s", plan, return_date
        )

        return {
            "tool_plan": plan,
            "return_date": return_date   # None for one-way, "YYYY-MM-DD" for round-trip
        }

    async def call_search(state: FlightSearchState):
        return await search_node(state, executor)

    # ── BUILD GRAPH ───────────────────────────────────────────────────────────
    workflow = StateGraph(FlightSearchState)
    workflow.add_node("planner",   call_planner)
    workflow.add_node("search",    call_search)
    workflow.add_node("normalize", normalize_node)
    workflow.add_node("optimize",  optimize_node)
    workflow.add_node("explain",   explain_node)

    workflow.set_entry_point("planner")
    workflow.add_edge("planner",   "search")
    workflow.add_edge("search",    "normalize")
    workflow.add_edge("normalize", "optimize")
    workflow.add_edge("optimize",  "explain")
    workflow.add_edge("explain",   END)

    return workflow.compile()


# ── TERMINAL INTERFACE ────────────────────────────────────────────────────────

async def main():
    mcp = MCPClient("http://localhost:8000/mcp")
    await mcp.connect()

    try:
        tools    = await ToolLoader(mcp, ["flight"]).load()
        planner  = PlannerAgent(tools)
        executor = ToolExecutor(mcp)
        app      = get_compiled_app(planner, executor)

        print("\n✈️  Flight Assistant Ready! (Type 'exit' to stop)")
        while True:
            user_input = input("\nHow can I help you with flights? > ").strip()
            if user_input.lower() in ["exit", "quit", "q"]:
                break
            if not user_input:
                continue

            print(f"Searching for: {user_input}...")
            result = await app.ainvoke({"user_query": user_input})
            print("\n--- ASSISTANT RESPONSE ---\n")
            print(result.get("explanation", "No response."))
            print("\n" + "-" * 30)

    except KeyboardInterrupt:
        print("\nExiting gracefully...")
    finally:
        await mcp.close()


if __name__ == "__main__":
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
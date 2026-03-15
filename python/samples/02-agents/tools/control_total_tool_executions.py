# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Annotated

from agent_framework import tool
from agent_framework.openai import OpenAIResponsesClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
This sample demonstrates all the ways to control how many times tools are
executed during an agent run.  There are three complementary mechanisms:

1. ``max_iterations`` (on the chat client) — caps the number of **LLM
   roundtrips**.  Each roundtrip may invoke one or more tools in parallel.

2. ``max_function_calls`` (on the chat client) — caps the **total number of
   individual function invocations** across all iterations within a single
   request.  This is the primary knob for cost control. If the tool is called multiple
   times in one iteration, those will execute, after that it will stop working. For example,
   if max_invocations is 3 and the tool is called 5 times in a single iteration,
   these will complete, but any subsequent calls to the tool (in the same or future iterations)
   will raise a ToolException.

3. ``max_invocations`` (on a tool) — caps the **lifetime invocation count**
   of a specific tool instance.  The counter is never automatically reset,
   so it accumulates across requests when tools are singletons.

   Because ``max_invocations`` is tracked on the ``FunctionTool`` *instance*,
   wrapping the same callable with ``@tool`` multiple times creates independent
   counters.  This lets you give different agents different invocation budgets
   for the same underlying function.

Choose the right mechanism for your scenario:
• Prevent runaway LLM loops  →  ``max_iterations``
• Best-effort cap on tool execution cost per request  →  ``max_function_calls``
  (checked between iterations; a single batch of parallel calls may overshoot)
• Best-effort limit a specific expensive tool globally  →  ``max_invocations``
• Per-agent limits on shared tools  →  wrap the callable separately per agent
"""


# --- Tool definitions ---


# NOTE: approval_mode="never_require" is for sample brevity.
# Use "always_require" in production; see function_tool_with_approval.py.
@tool(approval_mode="never_require")
def search_web(query: Annotated[str, "The search query to look up."]) -> str:
    """Search the web for information."""
    return f"Results for '{query}': [page1, page2, page3]"


@tool(approval_mode="never_require")
def get_weather(city: Annotated[str, "The city to get the weather for."]) -> str:
    """Get the current weather for a city."""
    return f"Weather in {city}: Sunny, 22°C"


@tool(approval_mode="never_require", max_invocations=2)
def call_expensive_api(
    prompt: Annotated[str, "The prompt to send to the expensive API."],
) -> str:
    """Call a very expensive external API. Limited to 2 calls ever."""
    return f"Expensive result for '{prompt}'"


# --- Scenario 1: max_iterations (limit LLM roundtrips) ---


async def scenario_max_iterations():
    """Demonstrate max_iterations: limits how many times we loop back to the LLM.

    Each iteration may invoke one or more tools in parallel, so this does NOT
    directly limit the total number of function executions.
    """
    print("=" * 60)
    print("Scenario 1: max_iterations — limit LLM roundtrips")
    print("=" * 60)

    client = OpenAIResponsesClient()

    # 1. Set max_iterations to 3 — the tool loop will run at most 3 roundtrips
    #    to the model before forcing a text response.
    client.function_invocation_configuration["max_iterations"] = 3
    print(f"  max_iterations = {client.function_invocation_configuration['max_iterations']}")

    agent = client.as_agent(
        name="ResearchAgent",
        instructions=(
            "You are a research assistant. Use the search_web tool to answer "
            "the user's question. Search for multiple aspects of the topic."
        ),
        tools=[search_web, get_weather],
    )

    response = await agent.run("Tell me about the weather in Paris, London, and Tokyo.")
    print(f"  Response: {response.text[:200]}...")
    print()


# --- Scenario 2: max_function_calls (limit total tool executions per request) ---


async def scenario_max_function_calls():
    """Demonstrate max_function_calls: caps total individual tool invocations.

    Unlike max_iterations, this counts every individual function execution —
    even when several tools run in parallel within a single iteration.
    """
    print("=" * 60)
    print("Scenario 2: max_function_calls — limit total tool executions")
    print("=" * 60)

    client = OpenAIResponsesClient()

    # 1. Allow many iterations but cap total function calls to 4.
    #    If the model requests 3 parallel searches per iteration, after 2
    #    iterations (6 calls) the limit is hit and the loop stops.
    client.function_invocation_configuration["max_iterations"] = 20
    client.function_invocation_configuration["max_function_calls"] = 4
    print(f"  max_iterations    = {client.function_invocation_configuration['max_iterations']}")
    print(f"  max_function_calls = {client.function_invocation_configuration['max_function_calls']}")

    agent = client.as_agent(
        name="ResearchAgent",
        instructions=(
            "You are a research assistant. Use the search_web and get_weather "
            "tools to answer the user's question comprehensively."
        ),
        tools=[search_web, get_weather],
    )

    response = await agent.run(
        "Search for the weather in Paris, London, Tokyo, "
        "New York, and Sydney, and also search for best travel tips."
    )
    print(f"  Response: {response.text[:200]}...")
    print()


# --- Scenario 3: max_invocations (lifetime limit on a specific tool) ---


async def scenario_max_invocations():
    """Demonstrate max_invocations: caps how many times a specific tool instance
    can be called across ALL requests.

    Note: this counter lives on the tool instance, so for module-level tools
    it accumulates globally. Use tool.invocation_count to inspect or reset.
    """
    print("=" * 60)
    print("Scenario 3: max_invocations — lifetime cap on a tool")
    print("=" * 60)

    agent = OpenAIResponsesClient().as_agent(
        name="APIAgent",
        instructions="Use call_expensive_api when asked to analyze something.",
        tools=[call_expensive_api],
    )
    session = agent.create_session()

    # 1. First call — succeeds (invocation_count: 0 → 1)
    print(f"  Before call 1: invocation_count = {call_expensive_api.invocation_count}")
    response = await agent.run("Analyze the market trends for AI.", session=session)
    print(f"  After call 1:  invocation_count = {call_expensive_api.invocation_count}")
    print(f"  Response: {response.text[:150]}...")

    # 2. Second call — succeeds (invocation_count: 1 → 2)
    response = await agent.run("Analyze the market trends for cloud computing.", session=session)
    print(f"  After call 2:  invocation_count = {call_expensive_api.invocation_count}")
    print(f"  Response: {response.text[:150]}...")

    # 3. Third call — tool refuses (max_invocations=2 reached)
    response = await agent.run("Analyze the market trends for quantum computing.", session=session)
    print(f"  After call 3:  invocation_count = {call_expensive_api.invocation_count}")
    print(f"  Response: {response.text[:150]}...")

    # 4. Reset the counter to allow more calls
    print()
    print("  Resetting invocation_count to 0...")
    call_expensive_api.invocation_count = 0
    print(f"  invocation_count = {call_expensive_api.invocation_count}")
    print()


# --- Scenario 4: Per-agent limits via separate tool wrappers ---


async def scenario_per_agent_tool_limits():
    """Demonstrate per-agent max_invocations using separate tool wrappers.

    Because max_invocations is tracked on the FunctionTool *instance*, you can
    wrap the same callable with ``@tool`` multiple times to get independent
    counters for different agents.  This is useful when two agents share the
    same underlying function but should have different invocation budgets.
    """
    print("=" * 60)
    print("Scenario 4: Per-agent limits via separate tool wrappers")
    print("=" * 60)

    # The underlying callable — a plain function, no decorator.
    def _do_lookup(query: Annotated[str, "Search query."]) -> str:
        """Look up information."""
        return f"Lookup result for '{query}'"

    # Wrap it twice with different limits. Each wrapper is a separate
    # FunctionTool instance with its own invocation_count.
    agent_a_lookup = tool(name="lookup", approval_mode="never_require", max_invocations=2)(_do_lookup)
    agent_b_lookup = tool(name="lookup", approval_mode="never_require", max_invocations=5)(_do_lookup)

    client = OpenAIResponsesClient()
    agent_a = client.as_agent(
        name="AgentA",
        instructions="Use the lookup tool to answer questions.",
        tools=[agent_a_lookup],
    )
    agent_b = client.as_agent(
        name="AgentB",
        instructions="Use the lookup tool to answer questions.",
        tools=[agent_b_lookup],
    )

    print(f"  agent_a_lookup.max_invocations = {agent_a_lookup.max_invocations}")
    print(f"  agent_b_lookup.max_invocations = {agent_b_lookup.max_invocations}")

    # Agent A uses its budget
    session_a = agent_a.create_session()
    await agent_a.run("Look up AI trends", session=session_a)
    await agent_a.run("Look up cloud trends", session=session_a)

    # Agent B's counter is independent — still at 0
    session_b = agent_b.create_session()
    await agent_b.run("Look up quantum computing", session=session_b)

    print(f"  agent_a_lookup.invocation_count = {agent_a_lookup.invocation_count}  (limit {agent_a_lookup.max_invocations})")
    print(f"  agent_b_lookup.invocation_count = {agent_b_lookup.invocation_count}  (limit {agent_b_lookup.max_invocations})")
    print("  → Agent A hit its limit; Agent B used 1 of 5.")
    print()


# --- Scenario 5: Combining all three mechanisms ---


async def scenario_combined():
    """Demonstrate using all three mechanisms together for defense in depth."""
    print("=" * 60)
    print("Scenario 5: Combined — all mechanisms together")
    print("=" * 60)

    client = OpenAIResponsesClient()

    # 1. Configure the client with both iteration and function call limits.
    client.function_invocation_configuration["max_iterations"] = 5       # max 5 LLM roundtrips
    client.function_invocation_configuration["max_function_calls"] = 8   # max 8 total tool calls
    print(f"  max_iterations     = {client.function_invocation_configuration['max_iterations']}")
    print(f"  max_function_calls = {client.function_invocation_configuration['max_function_calls']}")

    # 2. Use a tool with a lifetime invocation limit.
    @tool(approval_mode="never_require", max_invocations=3)
    def premium_lookup(topic: Annotated[str, "Topic to look up."]) -> str:
        """Look up premium data (max 3 calls ever)."""
        return f"Premium data for '{topic}'"

    print(f"  premium_lookup.max_invocations = {premium_lookup.max_invocations}")

    agent = client.as_agent(
        name="MultiToolAgent",
        instructions="Use all available tools to answer comprehensively.",
        tools=[search_web, get_weather, premium_lookup],
    )

    # 3. Run a query that could trigger many tool calls.
    response = await agent.run(
        "Research the weather and tourism info for Paris, London, Tokyo, "
        "New York, and Sydney. Use premium_lookup for the top 3 cities."
    )
    print(f"  Response: {response.text[:200]}...")
    print(f"  premium_lookup.invocation_count = {premium_lookup.invocation_count}")
    print()


# --- Entry point ---


async def main():
    await scenario_max_iterations()
    await scenario_max_function_calls()
    await scenario_max_invocations()
    await scenario_per_agent_tool_limits()
    await scenario_combined()


"""
Sample output:

============================================================
Scenario 1: max_iterations — limit LLM roundtrips
============================================================
  max_iterations = 3
  Response: The weather in Paris is sunny at 22°C, London is sunny at 22°C, and Tokyo is sunny at 22°C...
============================================================
Scenario 2: max_function_calls — limit total tool executions
============================================================
  max_iterations    = 20
  max_function_calls = 4
  Response: Based on my research, Paris is sunny at 22°C, London is sunny at 22°C...
============================================================
Scenario 3: max_invocations — lifetime cap on a tool
============================================================
  Before call 1: invocation_count = 0
  After call 1:  invocation_count = 1
  Response: Based on the analysis, the AI market is showing strong growth trends...
  After call 2:  invocation_count = 2
  Response: The cloud computing market continues to expand with key trends in...
  After call 3:  invocation_count = 2
  Response: I'm unable to use the analysis tool right now as it has reached its limit...

  Resetting invocation_count to 0...
  invocation_count = 0

============================================================
Scenario 4: Per-agent limits via separate tool wrappers
============================================================
  agent_a_lookup.max_invocations = 2
  agent_b_lookup.max_invocations = 5
  agent_a_lookup.invocation_count = 2  (limit 2)
  agent_b_lookup.invocation_count = 1  (limit 5)
  → Agent A hit its limit; Agent B used 1 of 5.

============================================================
Scenario 5: Combined — all mechanisms together
============================================================
  max_iterations     = 5
  max_function_calls = 8
  premium_lookup.max_invocations = 3
  Response: Here's a comprehensive overview of the weather and tourism for the cities...
  premium_lookup.invocation_count = 3
"""

if __name__ == "__main__":
    asyncio.run(main())

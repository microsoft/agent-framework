# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from agent_framework import Agent, FunctionInvocationContext, agent_middleware, tool
from agent_framework._middleware import AgentContext
from agent_framework.openai import OpenAIResponsesClient

"""
Agent-as-Tool with Conversation ID Propagation Example

Demonstrates how a parent agent's conversation_id is automatically propagated
to sub-agents wrapped as tools via as_tool(). This enables correlating
multi-agent conversations in storage systems.

The middleware below is ONLY for observability — to print the conversation_id
at each stage so you can verify the propagation. It is NOT required for the
feature to work. The propagation happens automatically at the framework level.

NOTE: conversation_id propagation requires a chat client that returns
conversation_id in its responses (e.g., OpenAI Responses API).
"""


# --- Observability middleware (not required for the feature) ---


@agent_middleware
async def log_conversation_id(context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
    """Prints the conversation_id seen by each agent. Only for demonstration."""
    agent_name = context.agent.name if hasattr(context.agent, "name") else "unknown"
    conv_id = (context.options or {}).get("conversation_id")
    additional = (context.options or {}).get("additional_function_arguments", {})
    parent_id = additional.get("parent_conversation_id")
    print(f"  [{agent_name}] conversation_id={conv_id}, parent_conversation_id={parent_id}")
    await call_next()


async def log_tool_kwargs(
    context: FunctionInvocationContext,
    call_next: Callable[[], Awaitable[None]],
) -> None:
    """Prints the kwargs forwarded to a tool. Only for demonstration."""
    conv_id = context.kwargs.get("conversation_id")
    parent_id = context.kwargs.get("parent_conversation_id")
    print(f"  [tool:{context.function.name}] conversation_id={conv_id}, parent_conversation_id={parent_id}")
    await call_next()


# --- Application code ---


# This tool is NOT required for conversation_id propagation to work.
# It is included only to show the parent_conversation_id arriving via **kwargs.
# NOTE: approval_mode="never_require" is for sample brevity.
@tool(approval_mode="never_require")
def lookup_info(query: str, **kwargs: Any) -> str:
    """Look up information for a given query.

    Args:
        query: The search query.

    Keyword Args:
        kwargs: Runtime context forwarded by the framework, including
            parent_conversation_id if the parent agent propagated one.

    Returns:
        The lookup result.
    """
    parent_id = kwargs.get("parent_conversation_id")
    return f"Results for '{query}' (tracked under parent conversation {parent_id})"


async def main() -> None:
    print("=== Agent-as-Tool: Conversation ID Propagation ===\n")

    client = OpenAIResponsesClient()

    # Create a specialized research agent
    researcher = Agent(
        client=client,
        name="ResearchAgent",
        instructions="You are a research assistant. Use the lookup_info tool to find information.",
        tools=[lookup_info],
        middleware=[log_conversation_id],
        function_middleware=[log_tool_kwargs],
    )

    # Wrap the research agent as a tool for the coordinator
    research_tool = researcher.as_tool(
        name="research",
        description="Delegate research tasks to a specialized research agent",
        arg_name="task",
        arg_description="The research task to perform",
    )

    # Create coordinator with the same observability middleware
    coordinator = Agent(
        client=client,
        name="CoordinatorAgent",
        instructions=(
            "You are a coordinator. When the user asks a question, delegate to the research tool to find the answer."
        ),
        tools=[research_tool],
        middleware=[log_conversation_id],
        function_middleware=[log_tool_kwargs],
    )

    # Run — watch the printed output to see conversation_id flow:
    #   1. CoordinatorAgent gets a conversation_id from the API
    #   2. The tool invocation forwards it to the research tool's **kwargs
    #   3. ResearchAgent receives it as parent_conversation_id in its options
    #   4. ResearchAgent's own tools see it via **kwargs
    response = await coordinator.run("What are the latest developments in quantum computing?")

    print(f"\nCoordinator: {response.text}")


if __name__ == "__main__":
    asyncio.run(main())

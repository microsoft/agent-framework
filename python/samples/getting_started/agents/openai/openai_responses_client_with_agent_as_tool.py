# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import Awaitable, Callable

from agent_framework import FunctionInvocationContext
from agent_framework.openai import OpenAIResponsesClient

"""
OpenAI Responses Client Agent-as-Tool Example

Demonstrates hierarchical agent architectures where one agent delegates
work to specialized sub-agents wrapped as tools using as_tool().

This pattern is useful when you want a coordinator agent to orchestrate
multiple specialized agents, each focusing on specific tasks.
"""


async def logging_middleware(
    context: FunctionInvocationContext,
    next: Callable[[FunctionInvocationContext], Awaitable[None]],
) -> None:
    """Middleware that logs tool invocations to show the delegation flow."""
    print(f"[Calling tool: {context.function.name}]")
    print(f"[Request: {context.arguments}]")

    await next(context)

    print(f"[Response: {context.result}]")


async def main() -> None:
    print("=== OpenAI Responses Client Agent-as-Tool Pattern ===")

    client = OpenAIResponsesClient()

    # Create a specialized writer agent
    writer = client.as_agent(
        name="WriterAgent",
        instructions="You are a creative writer. Write short, engaging content.",
    )

    # Convert writer agent to a tool using as_tool()
    writer_tool = writer.as_tool(
        name="creative_writer",
        description="Generate creative content like taglines, slogans, or short copy",
        arg_name="request",
        arg_description="What to write",
    )

    # Create coordinator agent with writer as a tool
    coordinator = client.as_agent(
        name="CoordinatorAgent",
        instructions="You coordinate with specialized agents. Delegate writing tasks to the creative_writer tool.",
        tools=[writer_tool],
        middleware=[logging_middleware],
    )

    query = "Create a tagline for a coffee shop"
    print(f"User: {query}")
    result = await coordinator.run(query)
    print(f"Coordinator: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())

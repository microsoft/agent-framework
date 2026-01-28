# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import Awaitable, Callable
from typing import Annotated

from agent_framework import (
    AgentRunContext,
    ChatMessageStore,
    tool,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from pydantic import Field

"""
Thread Behavior Middleware Example

This sample demonstrates how middleware can access and track thread state across multiple agent runs.
The example shows:

- How AgentRunContext.thread property behaves across multiple runs
- How middleware can access conversation history through the thread
- The timing of when thread messages are populated (before vs after next() call)
- How to track thread state changes across runs

Key behaviors demonstrated:
1. First run: context.messages is populated, context.thread is initially empty (before next())
2. After next(): thread contains input message + response from agent
3. Second run: context.messages contains only current input, thread contains previous history
4. After next(): thread contains full conversation history (all previous + current messages)
"""

# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")

def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    from random import randint

    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def thread_tracking_middleware(
    context: AgentRunContext,
    next: Callable[[AgentRunContext], Awaitable[None]],
) -> None:
    """Middleware that tracks and logs thread behavior across runs."""
    thread_messages = []
    if context.thread and context.thread.message_store:
        thread_messages = await context.thread.message_store.list_messages()

    print(f"[Middleware pre-execution] Current input messages: {len(context.messages)}")
    print(f"[Middleware pre-execution] Thread history messages: {len(thread_messages)}")

    # Call next to execute the agent
    await next(context)

    # Check thread state after agent execution
    updated_thread_messages = []
    if context.thread and context.thread.message_store:
        updated_thread_messages = await context.thread.message_store.list_messages()

    print(f"[Middleware post-execution] Updated thread messages: {len(updated_thread_messages)}")


async def main() -> None:
    """Example demonstrating thread behavior in middleware across multiple runs."""
    print("=== Thread Behavior Middleware Example ===")

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    agent = AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        name="WeatherAgent",
        instructions="You are a helpful weather assistant.",
        tools=get_weather,
        middleware=[thread_tracking_middleware],
        # Configure agent with message store factory to persist conversation history
        chat_message_store_factory=ChatMessageStore,
    )

    # Create a thread that will persist messages between runs
    thread = agent.get_new_thread()

    print("\nFirst Run:")
    query1 = "What's the weather like in Tokyo?"
    print(f"User: {query1}")
    result1 = await agent.run(query1, thread=thread)
    print(f"Agent: {result1.text}")

    print("\nSecond Run:")
    query2 = "How about in London?"
    print(f"User: {query2}")
    result2 = await agent.run(query2, thread=thread)
    print(f"Agent: {result2.text}")


if __name__ == "__main__":
    asyncio.run(main())

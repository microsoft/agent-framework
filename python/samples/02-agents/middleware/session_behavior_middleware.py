# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import Awaitable, Callable
from typing import Annotated

from agent_framework import (
    AgentContext,
    InMemoryHistoryProvider,
    tool,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from pydantic import Field

# Load environment variables from .env file
load_dotenv()

"""
Thread Behavior MiddlewareTypes Example

This sample demonstrates how middleware can access and track session state across multiple agent runs.
The example shows:

- How AgentContext.session property behaves across multiple runs
- How middleware can access conversation history through the session
- The timing of when session messages are populated (before vs after call_next() call)
- How to track session state changes across runs

Key behaviors demonstrated:
1. First run: context.messages is populated, context.session is initially empty (before call_next())
2. After call_next(): session contains input message + response from agent
3. Second run: context.messages contains only current input, session contains previous history
4. After call_next(): session contains full conversation history (all previous + current messages)
"""


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production;
# see samples/02-agents/tools/function_tool_with_approval.py
# and samples/02-agents/tools/function_tool_with_approval_and_sessions.py.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    from random import randint

    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def thread_tracking_middleware(
    context: AgentContext,
    call_next: Callable[[], Awaitable[None]],
) -> None:
    """MiddlewareTypes that tracks and logs session behavior across runs."""
    session_message_count = 0
    if context.session:
        memory_state = context.session.state.get(InMemoryHistoryProvider.DEFAULT_SOURCE_ID, {})
        session_message_count = len(memory_state.get("messages", []))

    print(f"[MiddlewareTypes pre-execution] Current input messages: {len(context.messages)}")
    print(f"[MiddlewareTypes pre-execution] Session history messages: {session_message_count}")

    # Call call_next to execute the agent
    await call_next()

    # Check session state after agent execution
    updated_session_message_count = 0
    if context.session:
        memory_state = context.session.state.get(InMemoryHistoryProvider.DEFAULT_SOURCE_ID, {})
        updated_session_message_count = len(memory_state.get("messages", []))

    print(f"[MiddlewareTypes post-execution] Updated session messages: {updated_session_message_count}")


async def main() -> None:
    """Example demonstrating session behavior in middleware across multiple runs."""
    print("=== Session Behavior MiddlewareTypes Example ===")

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    agent = AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        name="WeatherAgent",
        instructions="You are a helpful weather assistant.",
        tools=get_weather,
        middleware=[thread_tracking_middleware],
    )

    # Create a session that will persist messages between runs
    session = agent.create_session()

    print("\nFirst Run:")
    query1 = "What's the weather like in Tokyo?"
    print(f"User: {query1}")
    result1 = await agent.run(query1, session=session)
    print(f"Agent: {result1.text}")

    print("\nSecond Run:")
    query2 = "How about in London?"
    print(f"User: {query2}")
    result2 = await agent.run(query2, session=session)
    print(f"Agent: {result2.text}")


if __name__ == "__main__":
    asyncio.run(main())

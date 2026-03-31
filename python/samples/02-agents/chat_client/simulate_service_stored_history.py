# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Annotated

from agent_framework import (
    Agent,
    FunctionInvocationContext,
    FunctionMiddleware,
    InMemoryHistoryProvider,
    Message,
    MiddlewareTermination,
)
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from pydantic import Field

"""
Compare Foundry agents with and without ``simulate_service_stored_history``.

This sample runs two otherwise identical Foundry agents with ``store=False`` so
history stays local for both runs.

The sample adds a function middleware that raises ``MiddlewareTermination``
immediately after the tool runs, so the request stops before a second model
call.

That early termination is the important difference:

- Without ``simulate_service_stored_history``, the synthesized tool result is
  still written to local history.
- With ``simulate_service_stored_history=True``, that synthesized tool result is
  not written to local history.

The simulated case matches service-side storage behavior. When a terminated
request never sends the tool result back to the service, that result also never
becomes part of the service-managed history.
"""

# Load environment variables from .env file
load_dotenv()


def lookup_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Return a deterministic weather result for the requested location."""
    return f"The weather in {location} is sunny."


class TerminateAfterToolMiddleware(FunctionMiddleware):
    """Stop the tool loop after the first tool finishes."""

    async def process(
        self,
        context: FunctionInvocationContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        """Run the tool, then terminate the loop with that tool result."""
        await call_next()
        raise MiddlewareTermination(result=context.result)


def _describe_message(message: Message) -> str:
    """Render one stored message in a compact, readable format."""
    parts: list[str] = []
    for content in message.contents:
        if content.type == "text" and content.text:
            parts.append(content.text)
        elif content.type == "function_call":
            parts.append(f"function_call -> {content.name}({content.arguments})")
        elif content.type == "function_result":
            parts.append(f"function_result -> {content.result}")
        else:
            parts.append(content.type)

    return f"{message.role}: {' | '.join(parts)}"


def _includes_tool_result(messages: list[Message]) -> bool:
    """Return whether any stored message contains a tool result."""
    return any(content.type == "function_result" for message in messages for content in message.contents)


async def main() -> None:
    """Run both comparison scenarios."""
    print("=== simulate_service_stored_history when middleware terminates the tool loop ===\n")

    # 1. Create one Foundry chat client that both agents will share.
    client = FoundryChatClient(credential=AzureCliCredential())
    query = "What is the weather in Seattle, and should I bring sunglasses?"

    # 2. Create and run the agent without simulate_service_stored_history.
    agent_without_simulation = Agent(
        client=client,
        instructions=(
            "You are a weather assistant. Call lookup_weather exactly once before answering "
            "any weather question, then summarize the tool result in one short paragraph."
        ),
        tools=[lookup_weather],
        context_providers=[InMemoryHistoryProvider()],
        middleware=[TerminateAfterToolMiddleware()],
        default_options={"tool_choice": "required", "store": False},
    )
    session_without_simulation = agent_without_simulation.create_session()
    await agent_without_simulation.run(
        query,
        session=session_without_simulation,
    )
    stored_messages_without_simulation = session_without_simulation.state[InMemoryHistoryProvider.DEFAULT_SOURCE_ID][
        "messages"
    ]

    print("=== Without simulate_service_stored_history ===")
    print("Loop terminated immediately after the tool finished.")
    print(f"Stored synthesized tool result: {_includes_tool_result(stored_messages_without_simulation)}")
    print("Stored history:")
    for index, message in enumerate(stored_messages_without_simulation, start=1):
        print(f"  {index}. {_describe_message(message)}")
    print()

    # 3. Create and run the agent with simulate_service_stored_history enabled.
    agent_with_simulation = Agent(
        client=client,
        instructions=(
            "You are a weather assistant. Call lookup_weather exactly once before answering "
            "any weather question, then summarize the tool result in one short paragraph."
        ),
        tools=[lookup_weather],
        context_providers=[InMemoryHistoryProvider()],
        middleware=[TerminateAfterToolMiddleware()],
        simulate_service_stored_history=True,
        default_options={"tool_choice": "required", "store": False},
    )
    session_with_simulation = agent_with_simulation.create_session()
    await agent_with_simulation.run(
        query,
        session=session_with_simulation,
    )
    stored_messages_with_simulation = session_with_simulation.state[InMemoryHistoryProvider.DEFAULT_SOURCE_ID][
        "messages"
    ]

    print("=== With simulate_service_stored_history=True ===")
    print("Loop terminated immediately after the tool finished.")
    print(f"Stored synthesized tool result: {_includes_tool_result(stored_messages_with_simulation)}")
    print("Stored history:")
    for index, message in enumerate(stored_messages_with_simulation, start=1):
        print(f"  {index}. {_describe_message(message)}")
    print()

    # 4. Summarize the effect of the flag.
    print(
        "Both runs used FoundryChatClient with store=False and terminated right after the tool. "
        "Without simulation, local history still stored the synthesized tool result. "
        "With simulation, local history stopped at the assistant function-call message instead, "
        "which matches service-side storage because the terminated tool result is never sent back to the service."
    )


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output:
=== simulate_service_stored_history when middleware terminates the tool loop ===

=== Without simulate_service_stored_history ===
Loop terminated immediately after the tool finished.
Stored synthesized tool result: True
Stored history:
  1. user: What is the weather in Seattle, and should I bring sunglasses?
  2. assistant: function_call -> lookup_weather({"location":"Seattle"})
  3. tool: function_result -> The weather in Seattle is sunny.

=== With simulate_service_stored_history=True ===
Loop terminated immediately after the tool finished.
Stored synthesized tool result: False
Stored history:
  1. user: What is the weather in Seattle, and should I bring sunglasses?
  2. assistant: function_call -> lookup_weather({"location":"Seattle"})

Both runs used FoundryChatClient with store=False and terminated right after
the tool. Without simulation, local history still stored the synthesized tool
result. With simulation, local history stopped at the assistant function-call
message instead, which matches service-side storage because the terminated tool
result is never sent back to the service.
"""

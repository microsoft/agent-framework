# Copyright (c) Microsoft. All rights reserved.

"""
Claude Agent with Function Approval

This sample demonstrates how to enforce ``approval_mode="always_require"`` on a
``FunctionTool`` when using ``ClaudeAgent``. Because the Claude Agent SDK runs
its own tool-calling loop, the standard agent-framework approval round-trip
(``FunctionApprovalRequestContent`` → ``FunctionApprovalResponseContent``) is
not available — the agent instead awaits an ``on_function_approval`` callback
inside the tool handler before executing the tool.

Key points:
- ``on_function_approval`` is set on ``ClaudeAgentOptions`` and receives a
  ``FunctionCallContent`` describing the pending call. It must return ``True``
  to allow execution or ``False`` to deny it. Async callbacks are also
  supported.
- If no callback is configured, calls to ``always_require`` tools are denied
  by default and the model receives an explanatory error so it can react.
- This callback is independent of Claude's built-in ``permission_mode`` /
  ``can_use_tool`` features, which gate the SDK's own shell/file actions.

Environment variables:
- ANTHROPIC_API_KEY: Your Anthropic API key.
"""

import asyncio
from random import randrange
from typing import Annotated

from agent_framework import Content, tool
from agent_framework.anthropic import ClaudeAgent
from dotenv import load_dotenv

load_dotenv()


# Always-require tool: execution must be gated by on_function_approval.
@tool(approval_mode="always_require")
def get_weather_detail(location: Annotated[str, "The city and state, e.g. San Francisco, CA"]) -> str:
    """Get a detailed weather report for a location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return (
        f"The weather in {location} is {conditions[randrange(0, len(conditions))]} "
        f"with a high of {randrange(10, 30)}C and humidity of 88%."
    )


def prompt_for_approval(call: Content) -> bool:
    """Synchronous approval prompt.

    The callback receives a ``FunctionCallContent`` so the operator can review
    the tool name and arguments before deciding. Returning ``True`` allows the
    call; returning ``False`` denies it and a tool-error is returned to the
    model.
    """
    print(f"\n[Function Approval Request]\n  Tool: {call.name}\n  Arguments: {call.arguments}")
    response = input("Approve this tool call? (y/n): ").strip().lower()
    return response in ("y", "yes")


async def prompt_for_approval_async(call: Content) -> bool:
    """Async approval prompt.

    Use an async callback when approval requires I/O (e.g. an HTTP call to a
    review service or queueing the request to a UI). ``input()`` is wrapped
    with ``asyncio.to_thread`` so the event loop is not blocked.
    """
    print(f"\n[Function Approval Request - async]\n  Tool: {call.name}\n  Arguments: {call.arguments}")
    response = await asyncio.to_thread(input, "Approve this tool call? (y/n): ")
    return response.strip().lower() in ("y", "yes")


async def run_with_sync_callback() -> None:
    print("\n=== Claude Agent: synchronous approval callback ===")
    agent = ClaudeAgent(
        instructions="You are a helpful weather assistant.",
        tools=[get_weather_detail],
        default_options={"on_function_approval": prompt_for_approval},
    )
    async with agent:
        query = "Give me the detailed weather for Seattle."
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result.text}")


async def run_with_async_callback() -> None:
    print("\n=== Claude Agent: asynchronous approval callback ===")
    agent = ClaudeAgent(
        instructions="You are a helpful weather assistant.",
        tools=[get_weather_detail],
        default_options={"on_function_approval": prompt_for_approval_async},
    )
    async with agent:
        query = "Give me the detailed weather for Tokyo."
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result.text}")


async def run_without_callback() -> None:
    """Default-deny demonstration.

    With no ``on_function_approval`` configured, the always-require tool is
    refused and the model receives an explanatory error, so it can apologise
    or try a different approach instead of silently failing.
    """
    print("\n=== Claude Agent: no callback configured (deny by default) ===")
    agent = ClaudeAgent(
        instructions="You are a helpful weather assistant.",
        tools=[get_weather_detail],
    )
    async with agent:
        query = "Give me the detailed weather for Paris."
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result.text}")


async def main() -> None:
    print("=== Claude Agent: Function approval enforcement ===")
    await run_with_sync_callback()
    await run_with_async_callback()
    await run_without_callback()


if __name__ == "__main__":
    asyncio.run(main())

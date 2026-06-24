# Copyright (c) Microsoft. All rights reserved.

"""
GitHub Copilot Agent with Function Approval

This sample demonstrates how to enforce ``approval_mode="always_require"`` on a
``FunctionTool`` when using ``GitHubCopilotAgent``. Because the Copilot CLI
runs its own tool-calling loop, the standard agent-framework approval
round-trip (``FunctionApprovalRequestContent`` → ``FunctionApprovalResponseContent``)
is not available — the agent instead awaits an ``on_function_approval``
callback inside the tool handler before executing the tool.

Key points:
- ``on_function_approval`` is set on ``GitHubCopilotOptions`` and receives a
  ``FunctionCallContent`` describing the pending call. It must return ``True``
  to allow execution or ``False`` to deny it. Async callbacks are also
  supported.
- If no callback is configured, calls to ``always_require`` tools are denied
  by default and the model receives an explanatory error so it can react.
- This callback is independent of ``on_permission_request``, which gates the
  Copilot SDK's *built-in* shell/file actions; ``on_function_approval`` gates
  agent-framework ``FunctionTool`` calls.

Environment variables (optional):
- GITHUB_COPILOT_CLI_PATH: Path to the Copilot CLI executable.
- GITHUB_COPILOT_MODEL: Model to use.
"""

import asyncio
from random import randrange
from typing import Annotated

from agent_framework import Content, tool
from agent_framework.github import GitHubCopilotAgent, GitHubCopilotOptions
from copilot.session import PermissionHandler
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


async def prompt_for_approval(call: Content) -> bool:
    """Async approval callback that prompts the user interactively.

    The callback receives a ``FunctionCallContent`` so the operator can review
    the tool name and arguments before deciding. Returning ``True`` allows the
    call; returning ``False`` denies it and a tool-error is returned to the
    model.

    Uses ``asyncio.to_thread`` so the event loop is not blocked by ``input()``.
    """
    print(f"\n  [Function Approval Request]\n  Tool: {call.name}\n  Arguments: {call.arguments}")
    response = (await asyncio.to_thread(input, "  Approve this tool call? (y/n): ")).strip().lower()
    return response in ("y", "yes")


def auto_approve(call: Content) -> bool:
    """Synchronous approval callback that always approves.

    Use a sync callback for simple, non-blocking decisions that don't require
    I/O (e.g. checking an allow-list of tool names).
    """
    print(f"\n  [Function Approval Request]\n  Tool: {call.name}\n  Arguments: {call.arguments}")
    print("  -> Auto-approved")
    return True


async def run_with_interactive_callback() -> None:
    """Demonstrates an interactive approval prompt before tool execution."""
    print("\n=== GitHub Copilot Agent: interactive approval callback ===")
    agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
        instructions="You are a helpful weather assistant.",
        tools=[get_weather_detail],
        default_options=GitHubCopilotOptions(
            on_function_approval=prompt_for_approval,
            on_permission_request=PermissionHandler.approve_all,
        ),
    )
    async with agent:
        query = "Give me the detailed weather for Seattle."
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}")


async def run_with_auto_approve_callback() -> None:
    """Demonstrates a synchronous callback that always approves."""
    print("\n=== GitHub Copilot Agent: synchronous auto-approve callback ===")
    agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
        instructions="You are a helpful weather assistant.",
        tools=[get_weather_detail],
        default_options=GitHubCopilotOptions(
            on_function_approval=auto_approve,
            on_permission_request=PermissionHandler.approve_all,
        ),
    )
    async with agent:
        query = "Give me the detailed weather for Tokyo."
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}")


async def run_without_callback() -> None:
    """Default-deny demonstration.

    With no ``on_function_approval`` configured, the always-require tool is
    refused and the model receives an explanatory error, so it can apologise
    or try a different approach instead of silently failing.
    """
    print("\n=== GitHub Copilot Agent: no callback configured (deny by default) ===")
    agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
        instructions="You are a helpful weather assistant.",
        tools=[get_weather_detail],
        default_options=GitHubCopilotOptions(on_permission_request=PermissionHandler.approve_all),
    )
    async with agent:
        query = "Give me the detailed weather for Paris."
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}")


async def main() -> None:
    print("=== GitHub Copilot Agent: Function approval enforcement ===")
    await run_with_interactive_callback()
    await run_with_auto_approve_callback()
    await run_without_callback()


if __name__ == "__main__":
    asyncio.run(main())

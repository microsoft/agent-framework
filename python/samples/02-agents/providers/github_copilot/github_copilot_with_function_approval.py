# Copyright (c) Microsoft. All rights reserved.

"""
GitHub Copilot Agent with Function Approval

This sample demonstrates how ``approval_mode="always_require"`` on a
``FunctionTool`` is enforced when using ``GitHubCopilotAgent``. Because the
Copilot CLI runs its own tool-calling loop, approval is enforced through the
Copilot SDK's native pre-execution hook (``on_pre_tool_use``) rather than the
standard agent-framework approval round-trip.

How it works:
- When you register a tool declared with ``approval_mode="always_require"`` and
  you do **not** supply your own ``on_pre_tool_use`` hook, the agent installs a
  default ``on_pre_tool_use`` hook that returns ``"ask"`` for that tool and
  defers (``None``) for all other tools.
- The ``"ask"`` decision routes to your ``on_permission_request`` handler, where
  you approve or deny the call. With the default deny-all permission handler,
  such a tool is therefore denied unless you wire an approving handler.
- If you supply your own ``on_pre_tool_use`` hook, it takes precedence and you
  are responsible for enforcing approval; the agent logs a warning naming any
  approval-required tool that your hook must handle.

Environment variables (optional):
- GITHUB_COPILOT_CLI_PATH: Path to the Copilot CLI executable.
- GITHUB_COPILOT_MODEL: Model to use.
"""

import asyncio
from random import randrange
from typing import Annotated

from agent_framework import tool
from agent_framework.github import GitHubCopilotAgent, GitHubCopilotOptions
from copilot.generated.rpc import PermissionDecisionReject
from copilot.session import (
    PermissionHandler,
    PermissionRequestResult,
    PreToolUseHookInput,
    PreToolUseHookOutput,
)
from copilot.session_events import PermissionRequest
from dotenv import load_dotenv

load_dotenv()


INSTRUCTIONS = (
    "You are a helpful weather assistant. Always answer weather questions by calling the "
    "get_weather_detail tool. Do not browse the web or use any other source."
)


# Always-require tool: execution is gated by the default on_pre_tool_use hook,
# which routes the decision to on_permission_request.
@tool(approval_mode="always_require")
def get_weather_detail(location: Annotated[str, "The city and state, e.g. San Francisco, CA"]) -> str:
    """Get a detailed weather report for a location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return (
        f"The weather in {location} is {conditions[randrange(0, len(conditions))]} "
        f"with a high of {randrange(10, 30)}C and humidity of 88%."
    )


def approve_all_requests(request: PermissionRequest, context: dict[str, str]) -> PermissionRequestResult:
    """Permission handler that approves every request, including the gated tool."""
    print(f"\n  [Permission requested: {request.kind}] -> approved")
    return PermissionHandler.approve_all(request, context)


def deny_all_requests(request: PermissionRequest, _context: dict[str, str]) -> PermissionRequestResult:
    """Permission handler that denies every request."""
    print(f"\n  [Permission requested: {request.kind}] -> denied")
    return PermissionDecisionReject(feedback="Denied by the operator's policy.")


async def run_with_approval() -> None:
    """The approval-required tool runs because on_permission_request approves it."""
    print("\n=== GitHub Copilot Agent: approval-required tool (approved) ===")
    agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
        instructions=INSTRUCTIONS,
        tools=[get_weather_detail],
        default_options=GitHubCopilotOptions(on_permission_request=approve_all_requests),
    )
    async with agent:
        query = "Give me the detailed weather for Seattle."
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}")


async def run_with_denial() -> None:
    """The approval-required tool is blocked because on_permission_request denies it."""
    print("\n=== GitHub Copilot Agent: approval-required tool (denied) ===")
    agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
        instructions=INSTRUCTIONS,
        tools=[get_weather_detail],
        default_options=GitHubCopilotOptions(on_permission_request=deny_all_requests),
    )
    async with agent:
        query = "Give me the detailed weather for Paris."
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}")


async def run_with_custom_hook() -> None:
    """A caller-supplied on_pre_tool_use hook takes precedence over the default.

    When you provide your own hook you own approval enforcement entirely, so the
    agent does not install its default ask-hook and logs a warning naming any
    ``always_require`` tool it will no longer auto-gate. Here the custom hook
    approves the tool directly by returning ``"allow"`` — note that, unlike the
    default ``"ask"`` flow, this does not route through ``on_permission_request``
    (so no permission request is raised for the tool).
    """
    print("\n=== GitHub Copilot Agent: custom on_pre_tool_use hook (takes precedence) ===")

    def my_pre_tool_use(hook_input: PreToolUseHookInput, _context: dict[str, str]) -> PreToolUseHookOutput | None:
        if hook_input.get("toolName") == "get_weather_detail":
            return {"permissionDecision": "allow", "permissionDecisionReason": "Allowed by custom policy."}
        return None

    agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
        instructions=INSTRUCTIONS,
        tools=[get_weather_detail],
        default_options=GitHubCopilotOptions(
            on_pre_tool_use=my_pre_tool_use,
            on_permission_request=approve_all_requests,
        ),
    )
    async with agent:
        query = "Give me the detailed weather for Tokyo."
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}")


async def main() -> None:
    print("=== GitHub Copilot Agent: Function approval enforcement ===")
    await run_with_approval()
    await run_with_denial()
    await run_with_custom_hook()


if __name__ == "__main__":
    asyncio.run(main())

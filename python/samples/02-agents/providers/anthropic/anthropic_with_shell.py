# Copyright (c) Microsoft. All rights reserved.

import asyncio
import subprocess
from typing import Any

from agent_framework import Agent, Message, tool
from agent_framework.anthropic import AnthropicClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Anthropic Client with Shell Tool Example

This sample demonstrates using @tool(approval_mode=...) with AnthropicClient
for executing bash commands locally. The bash tool tells the model it can
request shell commands, while the actual execution happens on YOUR machine
via a user-provided function.

SECURITY NOTE: This example executes real commands on your local machine.
Only enable this when you trust the agent's actions. Consider implementing
allowlists, sandboxing, or approval workflows for production use.
"""


@tool(approval_mode="always_require")
def run_bash(command: str) -> str:
    """Execute a bash command using subprocess and return the output."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        parts: list[str] = []
        if result.stdout:
            parts.append(result.stdout)
        if result.stderr:
            parts.append(f"stderr: {result.stderr}")
        parts.append(f"exit_code: {result.returncode}")
        return "\n".join(parts)
    except subprocess.TimeoutExpired:
        return "Command timed out after 30 seconds"
    except Exception as e:
        return f"Error executing command: {e}"


async def main() -> None:
    """Example showing how to use the shell tool with AnthropicClient."""
    print("=== Anthropic Agent with Shell Tool Example ===")
    print("NOTE: Commands will execute on your local machine.\n")

    client = AnthropicClient()
    shell = client.get_shell_tool(func=run_bash)
    agent = Agent(
        client=client,
        instructions="You are a helpful assistant that can execute bash commands to answer questions.",
        tools=[shell],
    )

    query = "Use bash to print 'Hello from Anthropic shell!' and show the current working directory"
    print(f"User: {query}")
    result = await run_with_approvals(query, agent)
    print(f"Result: {result}\n")


async def run_with_approvals(query: str, agent: Agent) -> Any:
    """Run the agent and handle shell approvals outside tool execution."""
    current_input: str | list[Any] = query
    while True:
        result = await agent.run(current_input)
        if not result.user_input_requests:
            return result

        next_input: list[Any] = [query]
        rejected = False
        for user_input_needed in result.user_input_requests:
            print(
                f"\nShell request: {user_input_needed.function_call.name}"
                f"\nArguments: {user_input_needed.function_call.arguments}"
            )
            user_approval = await asyncio.to_thread(input, "\nApprove shell command? (y/n): ")
            approved = user_approval.strip().lower() == "y"
            next_input.append(Message("assistant", [user_input_needed]))
            next_input.append(Message("user", [user_input_needed.to_function_approval_response(approved)]))
            if not approved:
                rejected = True
                break
        if rejected:
            print("\nShell command rejected. Stopping without additional approval prompts.")
            return "Shell command execution was rejected by user."
        current_input = next_input


if __name__ == "__main__":
    asyncio.run(main())

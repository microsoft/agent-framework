# Copyright (c) Microsoft. All rights reserved.

import asyncio
import subprocess
from typing import Any

from agent_framework import Agent, Message, tool
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
OpenAI Chat Client with Local Shell Tool Example

This sample demonstrates implementing a local shell tool using get_shell_tool(func=...)
that wraps Python's subprocess module. Unlike the hosted shell tool (get_shell_tool()),
local shell execution runs commands on YOUR machine, not in a remote container.

SECURITY NOTE: This example executes real commands on your local machine.
Only enable this when you trust the agent's actions. Consider implementing
allowlists, sandboxing, or approval workflows for production use.
"""


@tool(approval_mode="always_require")
def run_bash(command: str) -> str:
    """Execute a shell command locally and return stdout, stderr, and exit code."""
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
    """Example showing how to use a local shell tool with OpenAI."""
    print("=== OpenAI Agent with Local Shell Tool Example ===")
    print("NOTE: Commands will execute on your local machine.\n")

    client = OpenAIChatClient()
    local_shell_tool = client.get_shell_tool(
        func=run_bash,
    )

    agent = Agent(
        client=client,
        instructions="You are a helpful assistant that can run shell commands to help the user.",
        tools=[local_shell_tool],
    )

    query = "Use the run_bash tool to execute `python --version` and show only the command output."
    print(f"User: {query}")
    result = await run_with_approvals(query, agent)
    if isinstance(result, str):
        print(f"Agent: {result}\n")
        return
    if result.text:
        print(f"Agent: {result.text}\n")
    else:
        printed = False
        for message in result.messages:
            for content in message.contents:
                if content.type == "function_result" and content.result:
                    print(f"Agent (tool output): {content.result}\n")
                    printed = True
        if not printed:
            print("Agent: (no text output returned)\n")


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

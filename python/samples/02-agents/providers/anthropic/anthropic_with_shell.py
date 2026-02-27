# Copyright (c) Microsoft. All rights reserved.

import asyncio
import subprocess

from agent_framework import Agent, shell_tool
from agent_framework.anthropic import AnthropicClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Anthropic Client with Shell Tool Example

This sample demonstrates using ShellTool with AnthropicClient
for executing bash commands locally. The bash tool tells the model it can
request shell commands, while the actual execution happens on YOUR machine
via a user-provided function.

SECURITY NOTE: This example executes real commands on your local machine.
Only enable this when you trust the agent's actions. Consider implementing
allowlists, sandboxing, or approval workflows for production use.
"""


@shell_tool
def run_bash(command: str) -> str:
    """Execute a bash command using subprocess and return the output.

    Prints the command and asks the user for confirmation before running.
    """
    print(f"\n[Shell] Command: {command}")
    answer = input("[Shell] Execute? (y/n): ").strip().lower()
    if answer != "y":
        return "Command rejected by user."

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

    agent = Agent(
        client=client,
        instructions="You are a helpful assistant that can execute bash commands to answer questions.",
        tools=[run_bash],
    )

    query = "Use bash to print 'Hello from Anthropic shell!' and show the current working directory"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Result: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())

# Copyright (c) Microsoft. All rights reserved.

import asyncio
import subprocess

from agent_framework import Agent, shell_tool
from agent_framework.openai import OpenAIResponsesClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
OpenAI Responses Client with Local Shell Tool Example

This sample demonstrates implementing a local shell tool using ShellTool
that wraps Python's subprocess module. Unlike the hosted shell tool (get_hosted_shell_tool()),
local shell execution runs commands on YOUR machine, not in a remote container.

SECURITY NOTE: This example executes real commands on your local machine.
Only enable this when you trust the agent's actions. Consider implementing
allowlists, sandboxing, or approval workflows for production use.
"""


@shell_tool
def run_bash(command: str) -> str:
    """Execute a shell command locally and return stdout, stderr, and exit code.

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
            parts.append(f"stdout:\n{result.stdout}")
        if result.stderr:
            parts.append(f"stderr:\n{result.stderr}")
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

    client = OpenAIResponsesClient()
    agent = Agent(
        client=client,
        instructions="You are a helpful assistant that can run shell commands to help the user.",
        tools=[run_bash],
    )

    query = "What Python version is installed on this machine?"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result.text}\n")


if __name__ == "__main__":
    asyncio.run(main())

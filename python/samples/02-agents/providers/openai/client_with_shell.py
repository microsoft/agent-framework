# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
OpenAI Chat Client with Shell Tool Example

This sample demonstrates using get_shell_tool() with OpenAI Chat Client
for executing shell commands in a managed container environment hosted by OpenAI.

The shell tool allows the model to run commands like listing files, running scripts,
or performing system operations within a secure, sandboxed container.
"""


async def main() -> None:
    """Example showing how to use the shell tool with OpenAI Chat."""
    print("=== OpenAI Chat Client Agent with Shell Tool Example ===")

    client = OpenAIChatClient()

    # Create a hosted shell tool with the default auto container environment
    shell_tool = client.get_shell_tool()

    agent = Agent(
        client=client,
        instructions="You are a helpful assistant that can execute shell commands to answer questions.",
        tools=shell_tool,
    )

    query = "Use a shell command to show the current date and time"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Result: {result}\n")

    # Print shell-specific content details
    for message in result.messages:
        shell_calls = [c for c in message.contents if c.type == "shell_tool_call"]
        shell_results = [c for c in message.contents if c.type == "shell_tool_result"]

        if shell_calls:
            print(f"Shell commands: {shell_calls[0].commands}")
        if shell_results and shell_results[0].outputs:
            for output in shell_results[0].outputs:
                if output.stdout:
                    print(f"Stdout: {output.stdout}")
                if output.stderr:
                    print(f"Stderr: {output.stderr}")
                if output.exit_code is not None:
                    print(f"Exit code: {output.exit_code}")


if __name__ == "__main__":
    asyncio.run(main())

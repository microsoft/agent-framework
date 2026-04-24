# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Any

from agent_framework import Agent, Message
from agent_framework.openai import OpenAIChatClient
from agent_framework_tools.shell import LocalShellTool
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
OpenAI Chat Client with Local Shell Tool Example

This sample uses ``LocalShellTool`` from ``agent-framework-tools`` — the
framework-supplied cross-OS shell executor with safe defaults (approval
required, deny-list of destructive commands, timeout, output truncation,
workdir confinement).

Currently not all models support the shell tool. Refer to the OpenAI
documentation for the list of supported models:
https://developers.openai.com/api/docs/models/

SECURITY NOTE: This example executes real commands on your local machine.
``LocalShellTool`` requires approval by default; only accept commands you
understand.
"""


async def main() -> None:
    print("=== OpenAI Agent with LocalShellTool Example ===")
    print("NOTE: Commands will execute on your local machine.\n")

    client = OpenAIChatClient(model="gpt-5.4-nano")

    async with LocalShellTool() as shell:
        agent = Agent(
            client=client,
            instructions="You are a helpful assistant that can run shell commands to help the user.",
            tools=[client.get_shell_tool(func=shell.as_function())],
        )

        query = "Use the shell tool to execute `python --version` and show only the command output."
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

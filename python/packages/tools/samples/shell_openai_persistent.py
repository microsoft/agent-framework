# Copyright (c) Microsoft. All rights reserved.

"""LocalShellTool with the OpenAI Responses local-shell tool type.

Runs real commands on your local machine. The `LocalShellTool` applies the
default deny-list and requires approval for every command.
"""

from __future__ import annotations

import asyncio
from typing import Any

from agent_framework import Agent, Message
from agent_framework.openai import OpenAIChatClient
from agent_framework_tools.shell import LocalShellTool
from dotenv import load_dotenv

load_dotenv()


async def main() -> None:
    client = OpenAIChatClient(model="gpt-5.4-nano")
    async with LocalShellTool() as shell:
        agent = Agent(
            client=client,
            instructions="You are a helpful assistant that can run shell commands to help the user.",
            tools=[client.get_shell_tool(func=shell.as_function())],
        )

        query = "Use the shell tool to run `python --version` and show only the command output."
        print(f"User: {query}")
        result = await _run_with_approvals(query, agent)
        if isinstance(result, str):
            print(f"Agent: {result}\n")
            return
        if result.text:
            print(f"Agent: {result.text}\n")


async def _run_with_approvals(query: str, agent: Agent) -> Any:
    """Loop that approves shell commands on the console."""
    current_input: str | list[Any] = query
    while True:
        result = await agent.run(current_input)
        if not result.user_input_requests:
            return result

        next_input: list[Any] = [query]
        rejected = False
        for needed in result.user_input_requests:
            print(
                f"\nShell request: {needed.function_call.name}"
                f"\nArguments: {needed.function_call.arguments}"
            )
            ok = (await asyncio.to_thread(input, "\nApprove shell command? (y/n): ")).strip().lower() == "y"
            next_input.append(Message("assistant", [needed]))
            next_input.append(Message("user", [needed.to_function_approval_response(ok)]))
            if not ok:
                rejected = True
                break
        if rejected:
            return "Shell command execution was rejected by user."
        current_input = next_input


if __name__ == "__main__":
    asyncio.run(main())

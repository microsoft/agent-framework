# Copyright (c) Microsoft. All rights reserved.

"""ShellTool with approval workflow example.

Warning: While ShellTool provides built-in security checks, the safest approach
is to run shell commands in isolated environments (containers, VMs, sandboxes)
with restricted permissions and network access.
"""

import asyncio
import json
from typing import Any

from agent_framework import ChatAgent, ChatMessage, ShellTool
from agent_framework.openai import OpenAIChatClient
from agent_framework.shell_local import LocalShellExecutor


async def run_with_approval(agent: ChatAgent, query: str | list[Any]) -> str:
    """Run agent and handle approval requests for shell commands."""
    result = await agent.run(query)

    while result.user_input_requests:
        new_inputs: list[Any] = [query] if isinstance(query, str) else list(query)

        for request in result.user_input_requests:
            args = json.loads(request.function_call.arguments)  # type: ignore
            print("\n[Approval Required]")
            commands = args.get("commands", [])
            print(f"  Commands: {commands}")

            approval = input("  Approve? (y/n): ").strip().lower()
            approved = approval == "y"

            new_inputs.append(ChatMessage(role="assistant", contents=[request]))
            new_inputs.append(ChatMessage(role="user", contents=[request.to_function_approval_response(approved)]))

        result = await agent.run(new_inputs)

    return result.text


async def main():
    shell_tool = ShellTool(
        executor=LocalShellExecutor(),
        description="Execute shell commands to organize files",
        options={
            "approval_mode": "always_require",
            "working_directory": "/workspace",
            "allowlist_patterns": ["ls", "mkdir", "mv", "tree", "find"],
            "allowed_paths": ["/workspace"],
        },
    )

    agent = ChatAgent(
        chat_client=OpenAIChatClient(),
        instructions="You are a helpful assistant.",
        tools=[shell_tool.as_ai_function()],
    )

    print("Type 'quit' to exit\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except EOFError:
            break

        if user_input.lower() in ("quit", "exit"):
            break
        if not user_input:
            continue

        response = await run_with_approval(agent, user_input)
        print(f"\nAgent: {response}\n")


if __name__ == "__main__":
    asyncio.run(main())

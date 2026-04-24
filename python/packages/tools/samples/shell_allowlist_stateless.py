# Copyright (c) Microsoft. All rights reserved.

"""Stateless LocalShellTool with a strict allow-list (no approval loop).

Every command must match one of the allow-list regexes and the deny-list
still wins. Approval is disabled because the allow-list is doing the
gating. This is the safest fully-automatic configuration.
"""

from __future__ import annotations

import asyncio

from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient
from agent_framework_tools.shell import LocalShellTool, ShellPolicy
from dotenv import load_dotenv

load_dotenv()


async def main() -> None:
    client = OpenAIChatClient(model="gpt-5.4-nano")

    shell = LocalShellTool(
        mode="stateless",
        approval_mode="never_require",
        policy=ShellPolicy(
            allowlist=[
                r"^ls(\s|$)",
                r"^pwd$",
                r"^cat\s[^|;&]+$",
                r"^git\s+(status|log|diff)(\s|$)",
                r"^python\s+--version$",
            ],
        ),
        timeout=10,
    )

    agent = Agent(
        client=client,
        instructions=(
            "You can run a narrow set of read-only shell commands (ls, pwd, cat, "
            "git status/log/diff, python --version). Anything else will be rejected."
        ),
        tools=[client.get_shell_tool(func=shell.as_function())],
    )

    query = "Summarise the current directory and print the Python version."
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result.text}")


if __name__ == "__main__":
    asyncio.run(main())

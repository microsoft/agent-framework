# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient
from agent_framework.tools import LocalShellTool, ShellPolicy
from dotenv import load_dotenv

"""
LocalShellTool with command-text filtering (no approval loop).

WARNING: This is an educational example, not a safe production configuration.
Do not copy this approval-disabled setup into production. Use only an isolated,
disposable environment without secrets or valuable data.

The allow-list checks command text, not what the shell will execute. Embedded
commands in $(...) or backticks can pass these filters and run; patterns that
only check the start of a command can also allow extra operations. These filters
do not enforce read-only access or protect against malicious model instructions.
Commands run with the application's permissions and can access or change files
and other resources available to it. Human approval and separately enforced
isolation are not replaced by an allow-list.
"""

load_dotenv()


async def main() -> None:
    client = OpenAIChatClient(model="gpt-5.4-nano")

    shell = LocalShellTool(
        mode="stateless",
        # Unsafe for production as shown: these filters do not replace human approval or isolation.
        approval_mode="never_require",
        acknowledge_unsafe=True,
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
        instructions=("Use only these shell commands: ls, pwd, cat, git status/log/diff, python --version."),
        tools=[client.get_shell_tool(func=shell.as_function())],
    )

    query = "Summarise the current directory and print the Python version."
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result.text}")


if __name__ == "__main__":
    asyncio.run(main())

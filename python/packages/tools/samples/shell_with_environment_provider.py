# Copyright (c) Microsoft. All rights reserved.

"""LocalShellTool wired with a ShellEnvironmentProvider context provider.

The provider probes the underlying shell once per provider lifetime and
injects an instructions block describing the shell family, OS, working
directory, and a configurable list of CLI tools. This helps the model
emit commands in the correct idiom (e.g. PowerShell vs bash) and avoids
asking it to use tools that are not installed.

Two phases are demonstrated:

* **Stateless** mode — each ``run`` call spawns a fresh shell, so
  ``cd`` does not carry across calls.
* **Persistent** mode — a single long-lived shell process backs every
  call, so ``cd`` and exported environment variables persist.

Approval gating is disabled so the demo runs unattended. Real
applications should keep approval on, or use ``DockerShellTool``.
"""

from __future__ import annotations

import asyncio

from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv

from agent_framework_tools.shell import (
    LocalShellTool,
    ShellEnvironmentProvider,
    ShellEnvironmentProviderOptions,
)

load_dotenv()


def _print_snapshot(label: str, provider: ShellEnvironmentProvider) -> None:
    snapshot = provider.current_snapshot
    if snapshot is None:
        print(f"[{label}] no snapshot captured")
        return
    print(f"\n[{label}] snapshot:")
    print(f"  family            = {snapshot.family.value}")
    print(f"  os                = {snapshot.os_description}")
    print(f"  shell_version     = {snapshot.shell_version}")
    print(f"  working_directory = {snapshot.working_directory}")
    for tool, version in snapshot.tool_versions.items():
        print(f"  {tool:<17} = {version}")


async def _ask(agent: Agent, query: str) -> None:
    print(f"\nUser: {query}")
    result = await agent.run(query)
    if result.text:
        print(f"Agent: {result.text}")


async def main() -> None:
    """Run the stateless and persistent demos."""
    client = OpenAIChatClient(model="gpt-5.4-nano")
    options = ShellEnvironmentProviderOptions(
        probe_tools=("git", "python", "uv", "node"),
    )

    print("=== stateless mode ===")
    async with LocalShellTool(
        mode="stateless",
        approval_mode="never_require",
        acknowledge_unsafe=True,
    ) as shell:
        provider = ShellEnvironmentProvider(shell, options)
        agent = Agent(
            client=client,
            instructions="Use the shell tool to answer the user's question.",
            tools=[client.get_shell_tool(func=shell.as_function())],
            context_providers=[provider],
        )
        await _ask(agent, "Show me the current working directory.")
        await _ask(agent, "Now `cd ..` then show the working directory again.")
        await _ask(agent, "Show the working directory once more — did `cd` persist?")
        _print_snapshot("stateless", provider)

    print("\n=== persistent mode ===")
    async with LocalShellTool(
        mode="persistent",
        confine_workdir=False,
        approval_mode="never_require",
        acknowledge_unsafe=True,
    ) as shell:
        provider = ShellEnvironmentProvider(shell, options)
        agent = Agent(
            client=client,
            instructions="Use the shell tool to answer the user's question.",
            tools=[client.get_shell_tool(func=shell.as_function())],
            context_providers=[provider],
        )
        await _ask(agent, "Show me the current working directory.")
        await _ask(agent, "Now `cd ..` then show the working directory again.")
        await _ask(agent, "Show the working directory once more — did `cd` persist?")
        _print_snapshot("persistent", provider)


if __name__ == "__main__":
    asyncio.run(main())

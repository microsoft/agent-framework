# Copyright (c) Microsoft. All rights reserved.

"""
GitHub Copilot Agent with File Hooks

The Copilot CLI can load "file hooks" — hook definitions checked into a working directory
under `.github/hooks/`. A `sessionStart` hook, for example, runs a command on the host when
the session starts, before the agent sends its first request.

`GitHubCopilotAgent` leaves these hooks off by default so that a session behaves the same way
no matter which checkout it runs in, and so that a working directory cannot change what the
agent does without the application asking for it. Opt in with `enable_file_hooks=True` when the
working directory is one you control and its hooks are part of the behavior you want.

SECURITY NOTE: Hooks run as the user running your application, and they are not gated by
`on_permission_request` — that handler covers tool calls, which are a separate path. Only enable
file hooks for working directories you trust.

Run this sample from a directory that contains `.github/hooks/` to see the difference.
"""

import asyncio
import logging
from pathlib import Path

from agent_framework.github import GitHubCopilotAgent, GitHubCopilotOptions


async def default_behavior() -> None:
    """1. By default, hooks checked into the working directory are not loaded.

    The agent logs a warning when it finds hooks it is not loading, so the behavior is
    visible rather than silent. Enable logging for the package to see it.
    """
    print("=== 1. Default: file hooks are not loaded ===\n")

    agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
        instructions="You are a helpful assistant.",
    )

    async with agent:
        result = await agent.run("In one sentence, what can you help me with?")
        print(f"Agent: {result}\n")


async def opt_in_to_file_hooks() -> None:
    """2. Opt in for a working directory whose hooks you trust."""
    print("=== 2. Opted in: file hooks from the working directory are loaded ===\n")

    agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
        instructions="You are a helpful assistant.",
        default_options=GitHubCopilotOptions(enable_file_hooks=True),
    )

    async with agent:
        result = await agent.run("In one sentence, what can you help me with?")
        print(f"Agent: {result}\n")


async def main() -> None:
    # The agent warns through the "agent_framework.github_copilot" logger when the working
    # directory defines hooks that will not run.
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    hooks_directory = Path.cwd() / ".github" / "hooks"
    print(f"Working directory hooks: {hooks_directory} (exists: {hooks_directory.is_dir()})\n")

    await default_behavior()
    await opt_in_to_file_hooks()


if __name__ == "__main__":
    asyncio.run(main())

"""
Expected output (when the working directory defines hooks):

Working directory hooks: /path/to/repo/.github/hooks (exists: True)

=== 1. Default: file hooks are not loaded ===

WARNING: Not loading the file hooks defined in '/path/to/repo/.github/hooks': GitHubCopilotAgent
leaves enable_file_hooks off so a session behaves the same way in every working directory.
Set enable_file_hooks=True in default_options (or in per-run options) to run them.
Agent: I can help you write, review, and explain code.

=== 2. Opted in: file hooks from the working directory are loaded ===

Agent: I can help you write, review, and explain code.
"""

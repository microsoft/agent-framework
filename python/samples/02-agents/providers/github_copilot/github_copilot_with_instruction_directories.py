# Copyright (c) Microsoft. All rights reserved.

"""
GitHub Copilot Agent with Instruction Directories

This sample demonstrates how to configure custom instruction directories with
GitHubCopilotAgent. Instruction directories let the CLI load project-specific
or team-shared instruction files that shape the agent's behavior beyond the
default system message.

Use cases:
- Point the agent at a team-shared set of coding conventions.
- Load project-specific guidelines from a local `.copilot/instructions/` folder.
- Override or augment default instructions per session at runtime.

Environment variables (optional):
- GITHUB_COPILOT_CLI_PATH - Path to the Copilot CLI executable
- GITHUB_COPILOT_MODEL - Model to use (e.g., "gpt-5", "claude-sonnet-4")
"""

import asyncio
from pathlib import Path

from agent_framework.github import GitHubCopilotAgent
from copilot.generated.session_events import PermissionRequest
from copilot.session import PermissionRequestResult
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def prompt_permission(request: PermissionRequest, context: dict[str, str]) -> PermissionRequestResult:
    """Permission handler that prompts the user for approval."""
    print(f"\n[Permission Request: {request.kind}]")

    response = input("Approve? (y/n): ").strip().lower()
    if response in ("y", "yes"):
        return PermissionRequestResult(kind="approved")
    return PermissionRequestResult(kind="denied-interactively-by-user")


async def default_instructions_example() -> None:
    """Example of pointing the agent at project-specific instruction directories."""
    print("=== Instruction Directories (Default) ===\n")

    # 1. Define instruction directories.
    # These paths contain custom instruction files the CLI will load
    # alongside its built-in instructions.
    project_root = Path.cwd()
    instruction_dirs = [
        str(project_root / ".copilot" / "instructions"),
        str(project_root / "docs" / "agent-guidelines"),
    ]

    # 2. Create the agent with instruction directories in default_options.
    # These directories apply to every session created by this agent.
    agent = GitHubCopilotAgent(
        instructions="You are a helpful coding assistant.",
        default_options={
            "on_permission_request": prompt_permission,
            "instruction_directories": instruction_dirs,
        },
    )

    # 3. Run the agent — instruction files from those directories are loaded
    # automatically by the CLI when the session starts.
    async with agent:
        query = "Summarize the coding conventions I should follow in this project."
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}\n")


async def runtime_override_example() -> None:
    """Example of overriding instruction directories at runtime."""
    print("=== Instruction Directories (Runtime Override) ===\n")

    agent = GitHubCopilotAgent(
        instructions="You are a helpful assistant.",
        default_options={
            "on_permission_request": prompt_permission,
            "instruction_directories": ["/team/shared/instructions"],
        },
    )

    async with agent:
        # First call uses the default instruction directories
        query = "What instructions are you following?"
        print(f"User: {query}")
        result1 = await agent.run(query)
        print(f"Agent: {result1}\n")

        # Second call overrides with different instruction directories at runtime.
        # Runtime options take precedence over the defaults for that session.
        print("Overriding with project-specific instructions...\n")
        query2 = "Now what instructions are you following?"
        print(f"User: {query2}")
        result2 = await agent.run(
            query2,
            options={
                "instruction_directories": ["/project/specific/instructions"],
            },
        )
        print(f"Agent: {result2}\n")


async def main() -> None:
    print("=== GitHub Copilot Agent with Instruction Directories ===\n")

    await default_instructions_example()
    await runtime_override_example()


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:

=== GitHub Copilot Agent with Instruction Directories ===

=== Instruction Directories (Default) ===

User: Summarize the coding conventions I should follow in this project.
Agent: Based on the project instructions, you should follow these conventions...

=== Instruction Directories (Runtime Override) ===

User: What instructions are you following?
Agent: I'm following the team-shared coding guidelines which include...

Overriding with project-specific instructions...

User: Now what instructions are you following?
Agent: I'm now following the project-specific instructions which include...
"""

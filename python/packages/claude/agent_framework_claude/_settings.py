# Copyright (c) Microsoft. All rights reserved.

from typing import TypedDict

__all__ = ["ClaudeAgentSettings"]


class ClaudeAgentSettings(TypedDict, total=False):
    """Claude Agent settings.

    The settings are first loaded from environment variables with the prefix 'CLAUDE_AGENT_'.
    If the environment variables are not found, the settings can be loaded from a .env file
    with the encoding 'utf-8'.

    Keys:
        cli_path: The path to Claude CLI executable.
        model: The model to use (sonnet, opus, haiku).
        cwd: The working directory for Claude CLI.
        permission_mode: Permission mode (default, acceptEdits, plan, bypassPermissions).
        max_turns: Maximum number of conversation turns.
        max_budget_usd: Maximum budget in USD.
    """

    cli_path: str | None
    model: str | None
    cwd: str | None
    permission_mode: str | None
    max_turns: int | None
    max_budget_usd: float | None

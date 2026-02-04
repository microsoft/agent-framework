# Copyright (c) Microsoft. All rights reserved.

from typing import ClassVar

from agent_framework._pydantic import AFBaseSettings

__all__ = ["ClaudeAgentSettings"]


class ClaudeAgentSettings(AFBaseSettings):
    """Claude Agent settings.

    The settings are first loaded from environment variables with the prefix 'CLAUDE_AGENT_'.
    If the environment variables are not found, the settings can be loaded from a .env file
    with the encoding 'utf-8'. If the settings are not found in the .env file, the settings
    are ignored; however, validation will fail alerting that the settings are missing.

    Keyword Args:
        cli_path: The path to Claude CLI executable.
        model: The model to use (sonnet, opus, haiku).
        cwd: The working directory for Claude CLI.
        permission_mode: Permission mode (default, acceptEdits, plan, bypassPermissions).
        max_turns: Maximum number of conversation turns.
        max_budget_usd: Maximum budget in USD.
        env_file_path: If provided, the .env settings are read from this file path location.
        env_file_encoding: The encoding of the .env file, defaults to 'utf-8'.

    Examples:
        .. code-block:: python

            from agent_framework.anthropic import ClaudeAgentSettings

            # Using environment variables
            # Set CLAUDE_AGENT_MODEL=sonnet
            # CLAUDE_AGENT_PERMISSION_MODE=default

            # Or passing parameters directly
            settings = ClaudeAgentSettings(model="sonnet")

            # Or loading from a .env file
            settings = ClaudeAgentSettings(env_file_path="path/to/.env")
    """

    env_prefix: ClassVar[str] = "CLAUDE_AGENT_"

    cli_path: str | None = None
    model: str | None = None
    cwd: str | None = None
    permission_mode: str | None = None
    max_turns: int | None = None
    max_budget_usd: float | None = None

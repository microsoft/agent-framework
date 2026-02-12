# Copyright (c) Microsoft. All rights reserved.

from typing import TypedDict


class GitHubCopilotSettings(TypedDict, total=False):
    """GitHub Copilot model settings.

    The settings are first loaded from environment variables with the prefix 'GITHUB_COPILOT_'.
    If the environment variables are not found, the settings can be loaded from a .env file
    with the encoding 'utf-8'.

    Keys:
        cli_path: Path to the Copilot CLI executable.
            Can be set via environment variable GITHUB_COPILOT_CLI_PATH.
        model: Model to use (e.g., "gpt-5", "claude-sonnet-4").
            Can be set via environment variable GITHUB_COPILOT_MODEL.
        timeout: Request timeout in seconds.
            Can be set via environment variable GITHUB_COPILOT_TIMEOUT.
        log_level: CLI log level.
            Can be set via environment variable GITHUB_COPILOT_LOG_LEVEL.
    """

    cli_path: str | None
    model: str | None
    timeout: float | None
    log_level: str | None

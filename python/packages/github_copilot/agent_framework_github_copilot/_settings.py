# Copyright (c) Microsoft. All rights reserved.

from typing import ClassVar

from agent_framework._pydantic import AFBaseSettings


class GitHubCopilotSettings(AFBaseSettings):
    """GitHub Copilot model settings.

    The settings are first loaded from environment variables with the prefix 'GITHUB_COPILOT_'.
    If the environment variables are not found, the settings can be loaded from a .env file
    with the encoding 'utf-8'. If the settings are not found in the .env file, the settings
    are ignored; however, validation will fail alerting that the settings are missing.

    Keyword Args:
        cli_path: Path to the Copilot CLI executable.
            Can be set via environment variable GITHUB_COPILOT_CLI_PATH.
        model: Model to use (e.g., "gpt-5", "claude-sonnet-4").
            Can be set via environment variable GITHUB_COPILOT_MODEL.
        timeout: Request timeout in seconds.
            Can be set via environment variable GITHUB_COPILOT_TIMEOUT.
        log_level: CLI log level.
            Can be set via environment variable GITHUB_COPILOT_LOG_LEVEL.
        env_file_path: If provided, the .env settings are read from this file path location.
        env_file_encoding: The encoding of the .env file, defaults to 'utf-8'.

    Examples:
        .. code-block:: python

            from agent_framework_github_copilot import GitHubCopilotSettings

            # Using environment variables
            # Set GITHUB_COPILOT_MODEL=gpt-5
            settings = GitHubCopilotSettings()

            # Or passing parameters directly
            settings = GitHubCopilotSettings(model="claude-sonnet-4", timeout=120)

            # Or loading from a .env file
            settings = GitHubCopilotSettings(env_file_path="path/to/.env")
    """

    env_prefix: ClassVar[str] = "GITHUB_COPILOT_"

    cli_path: str | None = None
    model: str | None = None
    timeout: float | None = None
    log_level: str | None = None

# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import sys

if sys.version_info >= (3, 11):
    from typing import TypedDict  # pragma: no cover
else:
    from typing_extensions import TypedDict  # type: ignore # pragma: no cover


class AzureAISettings(TypedDict, total=False):
    """Azure AI Project settings.

    Settings are resolved in this order: explicit keyword arguments, values from an
    explicitly provided .env file, then environment variables with the prefix
    'AZURE_AI_'. If settings are missing after resolution, validation will fail.

    Keyword Args:
        project_endpoint: The Azure AI Project endpoint URL.
            Can be set via environment variable AZURE_AI_PROJECT_ENDPOINT.
        model: The name of the model to use.
            Can be set via environment variable AZURE_AI_MODEL.
        env_file_path: If provided, the .env settings are read from this file path location.
        env_file_encoding: The encoding of the .env file, defaults to 'utf-8'.

    Examples:
        .. code-block:: python

            from agent_framework.azure import AzureAISettings

            # Using environment variables
            # Set AZURE_AI_PROJECT_ENDPOINT=https://your-project.cognitiveservices.azure.com
            # Set AZURE_AI_MODEL=gpt-4
            settings = AzureAISettings()

            # Or passing parameters directly
            settings = AzureAISettings(
                project_endpoint="https://your-project.cognitiveservices.azure.com", model="gpt-4"
            )

            # Or loading from a .env file
            settings = AzureAISettings(env_file_path="path/to/.env")
    """

    project_endpoint: str | None
    model: str | None

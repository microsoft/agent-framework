# Copyright (c) Microsoft. All rights reserved.

from typing import ClassVar

from agent_framework._pydantic import AFBaseSettings
from pydantic import SecretStr


class GoogleAISettings(AFBaseSettings):
    """Google AI settings for Gemini API access.

    The settings are first loaded from environment variables with the prefix 'GOOGLE_AI_'.
    If the environment variables are not found, the settings can be loaded from a .env file
    with the encoding 'utf-8'. If the settings are not found in the .env file, the settings
    are ignored; however, validation will fail alerting that the settings are missing.

    Keyword Args:
        api_key: The Google AI API key.
        chat_model_id: The Google AI chat model ID (e.g., gemini-1.5-pro).
        env_file_path: If provided, the .env settings are read from this file path location.
        env_file_encoding: The encoding of the .env file, defaults to 'utf-8'.

    Examples:
        .. code-block:: python

            from agent_framework.google import GoogleAISettings

            # Using environment variables
            # Set GOOGLE_AI_API_KEY=your_api_key
            # GOOGLE_AI_CHAT_MODEL_ID=gemini-1.5-pro

            settings = GoogleAISettings()

            # Or passing parameters directly
            settings = GoogleAISettings(
                api_key="your_api_key",
                chat_model_id="gemini-1.5-pro"
            )

            # Or loading from a .env file
            settings = GoogleAISettings(env_file_path="path/to/.env")
    """

    env_prefix: ClassVar[str] = "GOOGLE_AI_"

    api_key: SecretStr | None = None
    chat_model_id: str | None = None


class VertexAISettings(AFBaseSettings):
    """Vertex AI settings for Google Cloud access.

    The settings are first loaded from environment variables with the prefix 'VERTEX_AI_'.
    If the environment variables are not found, the settings can be loaded from a .env file
    with the encoding 'utf-8'. If the settings are not found in the .env file, the settings
    are ignored; however, validation will fail alerting that the settings are missing.

    Keyword Args:
        project_id: The Google Cloud project ID.
        location: The Google Cloud region (e.g., us-central1).
        chat_model_id: The Vertex AI chat model ID (e.g., gemini-1.5-pro).
        credentials_path: Optional path to service account JSON file.
        env_file_path: If provided, the .env settings are read from this file path location.
        env_file_encoding: The encoding of the .env file, defaults to 'utf-8'.

    Examples:
        .. code-block:: python

            from agent_framework.google import VertexAISettings

            # Using environment variables
            # Set VERTEX_AI_PROJECT_ID=your-project-id
            # VERTEX_AI_LOCATION=us-central1
            # VERTEX_AI_CHAT_MODEL_ID=gemini-1.5-pro
            # GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json

            settings = VertexAISettings()

            # Or passing parameters directly
            settings = VertexAISettings(
                project_id="your-project-id",
                location="us-central1",
                chat_model_id="gemini-1.5-pro"
            )

            # Or loading from a .env file
            settings = VertexAISettings(env_file_path="path/to/.env")
    """

    env_prefix: ClassVar[str] = "VERTEX_AI_"

    project_id: str | None = None
    location: str | None = None
    chat_model_id: str | None = None
    credentials_path: str | None = None


# NOTE: Client implementations will be added in PR #2 and PR #4
# For PR #1, we're only setting up the package structure and settings

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
            settings = GoogleAISettings(api_key="your_api_key", chat_model_id="gemini-1.5-pro")

            # Or loading from a .env file
            settings = GoogleAISettings(env_file_path="path/to/.env")
    """

    env_prefix: ClassVar[str] = "GOOGLE_AI_"

    api_key: SecretStr | None = None
    chat_model_id: str | None = None


# NOTE: Client implementations will be added in a future PR
# For now, we're only setting up the package structure and settings

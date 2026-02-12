# Copyright (c) Microsoft. All rights reserved.

"""Azure Voice Live settings."""

from __future__ import annotations

from typing import ClassVar

from agent_framework._pydantic import AFBaseSettings
from pydantic import Field, SecretStr

__all__ = ["AzureVoiceLiveSettings"]


class AzureVoiceLiveSettings(AFBaseSettings):
    """Settings for Azure Voice Live client.

    The settings are first loaded from environment variables with the prefix 'AZURE_VOICELIVE_'.
    If the environment variables are not found, the settings can be loaded from a .env file
    with the encoding 'utf-8'. If the settings are not found in the .env file, the settings
    are ignored; however, validation will fail alerting that the settings are missing.

    Keyword Args:
        endpoint: The endpoint of the Azure Voice Live deployment. This value
            can be found in the Keys & Endpoint section when examining
            your resource from the Azure portal. Supports both https:// and wss:// protocols.
            Can be set via environment variable AZURE_VOICELIVE_ENDPOINT.
        api_key: The API key for the Azure deployment. This value can be
            found in the Keys & Endpoint section when examining your resource in
            the Azure portal. You can use either KEY1 or KEY2.
            Can be set via environment variable AZURE_VOICELIVE_API_KEY.
        model: The name of the Azure Voice Live model deployment. This value
            will correspond to the custom name you chose for your deployment
            when you deployed a model. This value can be found under
            Resource Management > Deployments in the Azure portal or, alternatively,
            under Management > Deployments in Azure AI Foundry.
            Can be set via environment variable AZURE_VOICELIVE_MODEL.
        api_version: The API version to use. The default value is "2025-10-01".
            Can be set via environment variable AZURE_VOICELIVE_API_VERSION.
        env_file_path: The path to the .env file to load settings from.
        env_file_encoding: The encoding of the .env file, defaults to 'utf-8'.

    Examples:
        .. code-block:: python

            from agent_framework_azure_voice_live import AzureVoiceLiveSettings

            # Using environment variables
            # Set AZURE_VOICELIVE_ENDPOINT=https://your-endpoint.cognitiveservices.azure.com
            # Set AZURE_VOICELIVE_MODEL=gpt-4o-realtime-preview
            # Set AZURE_VOICELIVE_API_KEY=your-key
            settings = AzureVoiceLiveSettings()

            # Or passing parameters directly
            settings = AzureVoiceLiveSettings(
                endpoint="https://your-endpoint.cognitiveservices.azure.com",
                model="gpt-4o-realtime-preview",
                api_key="your-key",
            )

            # Or loading from a .env file
            settings = AzureVoiceLiveSettings(env_file_path="path/to/.env")
    """

    env_prefix: ClassVar[str] = "AZURE_VOICELIVE_"

    endpoint: str | None = Field(
        None,
        description="Azure Voice Live endpoint URL (https:// or wss://)",
    )
    api_key: SecretStr | None = Field(
        None,
        description="API key for authentication",
    )
    model: str | None = Field(
        None,
        description="Model deployment name (e.g., gpt-4o-realtime-preview)",
    )
    api_version: str | None = Field(
        None,
        description="API version (default: 2025-10-01)",
    )

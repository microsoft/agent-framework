# Copyright (c) Microsoft. All rights reserved.

from typing import Any, ClassVar

from agent_framework._pydantic import AFBaseSettings
from agent_framework.exceptions import ServiceInitializationError
from agent_framework.openai._chat_client import OpenAIChatClientBase
from agent_framework.telemetry import use_telemetry
from foundry_local import FoundryLocalManager
from openai import AsyncOpenAI

__all__ = [
    "FoundryLocalChatClient",
]


class FoundryLocalSettings(AFBaseSettings):
    """Foundry local model settings.

    The settings are first loaded from environment variables with the prefix 'FOUNDRY_'.
    If the environment variables are not found, the settings can be loaded from a .env file
    with the encoding 'utf-8'. If the settings are not found in the .env file, the settings
    are ignored; however, validation will fail alerting that the settings are missing.

    Attributes:
        model_id: The name of the model deployment to use.
            (Env var FOUNDRY_LOCAL_MODEL_ID)
    Parameters:
        env_file_path: If provided, the .env settings are read from this file path location.
        env_file_encoding: The encoding of the .env file, defaults to 'utf-8'.
    """

    env_prefix: ClassVar[str] = "FOUNDRY_LOCAL_"

    model_id: str | None = None


@use_telemetry
class FoundryLocalChatClient(OpenAIChatClientBase):
    """Foundry Local Chat completion class."""

    foundry_local_manager: FoundryLocalManager

    def __init__(
        self,
        ai_model_id: str | None = None,
        bootstrap: bool = True,
        timeout: float | None = None,
    ) -> None:
        """Initialize a FoundryLocal ChatClient."""
        if not ai_model_id:
            settings = FoundryLocalSettings()
            if not settings.model_id:
                raise ServiceInitializationError(
                    "AI model ID must be provided either directly or "
                    "through the FOUNDRY_LOCAL_MODEL_ID environment variable."
                )
            ai_model_id = settings.model_id
        foundry_local = FoundryLocalManager(alias_or_model_id=ai_model_id, bootstrap=bootstrap, timeout=timeout)
        model_info = foundry_local.get_model_info(ai_model_id)
        if not model_info:
            raise ServiceInitializationError(f"Model with ID or alias '{ai_model_id}' not found in Foundry Local.")
        async_client = AsyncOpenAI(base_url=foundry_local.endpoint, api_key=foundry_local.api_key)
        args: dict[str, Any] = {
            "ai_model_id": model_info.id,
            "foundry_local_manager": foundry_local,
            "client": async_client,
        }
        super().__init__(**args)

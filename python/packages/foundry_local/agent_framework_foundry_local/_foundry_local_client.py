# Copyright (c) Microsoft. All rights reserved.

from typing import Any, ClassVar

from agent_framework import use_chat_middleware, use_function_invocation
from agent_framework._pydantic import AFBaseSettings
from agent_framework.exceptions import ServiceInitializationError
from agent_framework.observability import use_instrumentation
from agent_framework.openai._chat_client import OpenAIBaseChatClient
from foundry_local import FoundryLocalManager
from openai import AsyncOpenAI

__all__ = [
    "FoundryLocalChatClient",
]


class FoundryLocalSettings(AFBaseSettings):
    """Foundry local model settings.

    The settings are first loaded from environment variables with the prefix 'FOUNDRY_LOCAL_'.
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

    model_id: str


@use_function_invocation
@use_instrumentation
@use_chat_middleware
class FoundryLocalChatClient(OpenAIBaseChatClient):
    """Foundry Local Chat completion class."""

    def __init__(
        self,
        *,
        model_id: str | None = None,
        bootstrap: bool = True,
        timeout: float | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str = "utf-8",
        **kwargs: Any,
    ) -> None:
        """Initialize a FoundryLocal ChatClient."""
        settings = FoundryLocalSettings(
            model_id=model_id,  # type: ignore
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
        manager = FoundryLocalManager(alias_or_model_id=settings.model_id, bootstrap=bootstrap, timeout=timeout)
        model_info = manager.get_model_info(settings.model_id)
        if not model_info:
            raise ServiceInitializationError(
                f"Model with ID or alias '{settings.model_id}' not found in Foundry Local."
            )
        async_client = AsyncOpenAI(base_url=manager.endpoint, api_key=manager.api_key)
        args: dict[str, Any] = {
            "model_id": model_info.id,
            "client": async_client,
        }
        super().__init__(**args)
        self.manager = manager

# Copyright (c) Microsoft. All rights reserved.

import logging
from collections.abc import Mapping
from copy import copy
from typing import Any

from agent_framework.exceptions import ServiceInitializationError
from pydantic import ConfigDict, Field, validate_call

from openai import AsyncOpenAI

from ._openai_handler import OpenAIHandler
from ._openai_model_types import OpenAIModelTypes

logger: logging.Logger = logging.getLogger(__name__)


class OpenAIConfigBase(OpenAIHandler):
    """Internal class for configuring a connection to an OpenAI service."""

    @validate_call(config=ConfigDict(arbitrary_types_allowed=True))
    def __init__(
        self,
        ai_model_id: str = Field(min_length=1),
        api_key: str | None = Field(min_length=1),
        ai_model_type: OpenAIModelTypes | None = OpenAIModelTypes.CHAT,
        org_id: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        client: AsyncOpenAI | None = None,
        instruction_role: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a client for OpenAI services.

        This constructor sets up a client to interact with OpenAI's API, allowing for
        different types of AI model interactions, like chat or text completion.

        Args:
            ai_model_id (str): OpenAI model identifier. Must be non-empty.
                Default to a preset value.
            api_key (str): OpenAI API key for authentication.
                Must be non-empty. (Optional)
            ai_model_type (OpenAIModelTypes): The type of OpenAI
                model to interact with. Defaults to CHAT.
            org_id (str): OpenAI organization ID. This is optional
                unless the account belongs to multiple organizations.
            default_headers (Mapping[str, str]): Default headers
                for HTTP requests. (Optional)
            client (AsyncOpenAI): An existing OpenAI client, optional.
            instruction_role (str): The role to use for 'instruction'
                messages, for example, summarization prompts could use `developer` or `system`. (Optional)
            kwargs: Additional keyword arguments.

        """
        # Merge APP_INFO into the headers if it exists
        merged_headers = dict(copy(default_headers)) if default_headers else {}

        if not client:
            if not api_key:
                raise ServiceInitializationError("Please provide an api_key")
            client = AsyncOpenAI(
                api_key=api_key,
                organization=org_id,
                default_headers=merged_headers,
            )
        args = {
            "ai_model_id": ai_model_id,
            "client": client,
            "ai_model_type": ai_model_type,
        }
        if instruction_role:
            args["instruction_role"] = instruction_role
        super().__init__(**args, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        """Create a dict of the service settings."""
        client_settings = {
            "api_key": self.client.api_key,
            "default_headers": {k: v for k, v in self.client.default_headers.items() if k != "User-Agent"},
        }
        if self.client.organization:
            client_settings["org_id"] = self.client.organization
        base = self.model_dump(
            exclude={
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "api_type",
                "ai_model_type",
                "client",
            },
            by_alias=True,
            exclude_none=True,
        )
        base.update(client_settings)
        return base

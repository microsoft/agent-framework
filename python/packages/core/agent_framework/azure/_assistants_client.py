# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import sys
from collections.abc import Mapping
from typing import Any, ClassVar, Generic

from openai.lib.azure import AsyncAzureOpenAI

from .._settings import load_settings
from ..exceptions import ServiceInitializationError
from ..openai import OpenAIAssistantsClient
from ..openai._assistants_client import OpenAIAssistantsOptions
from ._entra_id_authentication import AzureCredentialTypes, AzureTokenProvider, resolve_credential_to_token_provider
from ._shared import AzureOpenAISettings, _apply_azure_defaults

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore # pragma: no cover
if sys.version_info >= (3, 11):
    from typing import TypedDict  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypedDict  # type: ignore # pragma: no cover


# region Azure OpenAI Assistants Options TypedDict


AzureOpenAIAssistantsOptionsT = TypeVar(
    "AzureOpenAIAssistantsOptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="OpenAIAssistantsOptions",
    covariant=True,
)


# endregion


class AzureOpenAIAssistantsClient(
    OpenAIAssistantsClient[AzureOpenAIAssistantsOptionsT], Generic[AzureOpenAIAssistantsOptionsT]
):
    """Azure OpenAI Assistants client."""

    DEFAULT_AZURE_API_VERSION: ClassVar[str] = "2024-05-01-preview"

    def __init__(
        self,
        *,
        deployment_name: str | None = None,
        assistant_id: str | None = None,
        assistant_name: str | None = None,
        assistant_description: str | None = None,
        thread_id: str | None = None,
        api_key: str | None = None,
        endpoint: str | None = None,
        base_url: str | None = None,
        api_version: str | None = None,
        token_endpoint: str | None = None,
        credential: AzureCredentialTypes | AzureTokenProvider | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncAzureOpenAI | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize an Azure OpenAI Assistants client.

        Keyword Args:
            deployment_name: The Azure OpenAI deployment name for the model to use.
                Can also be set via environment variable AZURE_OPENAI_CHAT_DEPLOYMENT_NAME.
            assistant_id: The ID of an Azure OpenAI assistant to use.
                If not provided, a new assistant will be created (and deleted after the request).
            assistant_name: The name to use when creating new assistants.
            assistant_description: The description to use when creating new assistants.
            thread_id: Default thread ID to use for conversations. Can be overridden by
                conversation_id property when making a request.
                If not provided, a new thread will be created (and deleted after the request).
            api_key: The API key to use. If provided will override the env vars or .env file value.
                Can also be set via environment variable AZURE_OPENAI_API_KEY.
            endpoint: The deployment endpoint. If provided will override the value
                in the env vars or .env file.
                Can also be set via environment variable AZURE_OPENAI_ENDPOINT.
            base_url: The deployment base URL. If provided will override the value
                in the env vars or .env file.
                Can also be set via environment variable AZURE_OPENAI_BASE_URL.
            api_version: The deployment API version. If provided will override the value
                in the env vars or .env file.
                Can also be set via environment variable AZURE_OPENAI_API_VERSION.
            token_endpoint: The token endpoint to request an Azure token.
                Can also be set via environment variable AZURE_OPENAI_TOKEN_ENDPOINT.
            credential: Azure credential or token provider for authentication. Accepts a
                ``TokenCredential``, ``AsyncTokenCredential``, or a callable that returns a
                bearer token string (sync or async), for example from
                ``azure.identity.get_bearer_token_provider()``.
            default_headers: The default headers mapping of string keys to
                string values for HTTP requests.
            async_client: An existing client to use.
            env_file_path: Use the environment settings file as a fallback
                to environment variables.
            env_file_encoding: The encoding of the environment settings file.

        Examples:
            .. code-block:: python

                from agent_framework.azure import AzureOpenAIAssistantsClient

                # Using environment variables
                # Set AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com
                # Set AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=gpt-4
                # Set AZURE_OPENAI_API_KEY=your-key
                client = AzureOpenAIAssistantsClient()

                # Or passing parameters directly
                client = AzureOpenAIAssistantsClient(
                    endpoint="https://your-endpoint.openai.azure.com", deployment_name="gpt-4", api_key="your-key"
                )

                # Or loading from a .env file
                client = AzureOpenAIAssistantsClient(env_file_path="path/to/.env")

                # Using custom ChatOptions with type safety:
                from typing import TypedDict
                from agent_framework.azure import AzureOpenAIAssistantsOptions


                class MyOptions(AzureOpenAIAssistantsOptions, total=False):
                    my_custom_option: str


                client: AzureOpenAIAssistantsClient[MyOptions] = AzureOpenAIAssistantsClient()
                response = await client.get_response("Hello", options={"my_custom_option": "value"})
        """
        azure_openai_settings = load_settings(
            AzureOpenAISettings,
            env_prefix="AZURE_OPENAI_",
            api_key=api_key,
            base_url=base_url,
            endpoint=endpoint,
            chat_deployment_name=deployment_name,
            api_version=api_version,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
            token_endpoint=token_endpoint,
        )
        _apply_azure_defaults(azure_openai_settings, default_api_version=self.DEFAULT_AZURE_API_VERSION)

        if not azure_openai_settings["chat_deployment_name"]:
            raise ServiceInitializationError(
                "Azure OpenAI deployment name is required. Set via 'deployment_name' parameter "
                "or 'AZURE_OPENAI_CHAT_DEPLOYMENT_NAME' environment variable."
            )

        # Resolve credential to token provider
        ad_token_provider = None
        if not async_client and not azure_openai_settings["api_key"] and credential:
            ad_token_provider = resolve_credential_to_token_provider(
                credential, azure_openai_settings["token_endpoint"]
            )

        if not async_client and not azure_openai_settings["api_key"] and not ad_token_provider:
            raise ServiceInitializationError("Please provide either api_key, credential, or a client.")

        # Create Azure client if not provided
        if not async_client:
            client_params: dict[str, Any] = {
                "api_version": azure_openai_settings["api_version"],
                "default_headers": default_headers,
            }

            if azure_openai_settings["api_key"]:
                client_params["api_key"] = azure_openai_settings["api_key"].get_secret_value()
            elif ad_token_provider:
                client_params["azure_ad_token_provider"] = ad_token_provider

            if azure_openai_settings["base_url"]:
                client_params["base_url"] = str(azure_openai_settings["base_url"])
            elif azure_openai_settings["endpoint"]:
                client_params["azure_endpoint"] = str(azure_openai_settings["endpoint"])

            async_client = AsyncAzureOpenAI(**client_params)

        super().__init__(
            model_id=azure_openai_settings["chat_deployment_name"],
            assistant_id=assistant_id,
            assistant_name=assistant_name,
            assistant_description=assistant_description,
            thread_id=thread_id,
            async_client=async_client,  # type: ignore[reportArgumentType]
            default_headers=default_headers,
        )

# Copyright (c) Microsoft. All rights reserved.

from collections.abc import Mapping
from typing import Any, TypeVar
from urllib.parse import urljoin

from azure.core.credentials import TokenCredential
from openai.lib.azure import AsyncAzureADTokenProvider, AsyncAzureOpenAI
from pydantic import ValidationError

from agent_framework import use_chat_middleware, use_function_invocation
from agent_framework.exceptions import ServiceInitializationError
from agent_framework.observability import use_observability
from agent_framework.openai._responses_client import OpenAIBaseResponsesClient

from ._shared import (
    AzureOpenAIConfigMixin,
    AzureOpenAISettings,
)

TAzureOpenAIResponsesClient = TypeVar("TAzureOpenAIResponsesClient", bound="AzureOpenAIResponsesClient")


@use_observability
@use_function_invocation
@use_chat_middleware
class AzureOpenAIResponsesClient(AzureOpenAIConfigMixin, OpenAIBaseResponsesClient):
    """Azure Responses completion class."""

    def __init__(
        self,
        api_key: str | None = None,
        deployment_name: str | None = None,
        endpoint: str | None = None,
        base_url: str | None = None,
        api_version: str | None = None,
        ad_token: str | None = None,
        ad_token_provider: AsyncAzureADTokenProvider | None = None,
        token_endpoint: str | None = None,
        credential: TokenCredential | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncAzureOpenAI | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        instruction_role: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize an AzureResponses service.

        Args:
            api_key: The optional api key. If provided, will override the value in the
                env vars or .env file.
            deployment_name: The optional deployment. If provided, will override the value
                (responses_deployment_name) in the env vars or .env file.
            endpoint: The optional deployment endpoint. If provided will override the value
                in the env vars or .env file.
            base_url: The optional deployment base_url. If provided will override the value
                in the env vars or .env file. Currently, the base_url must end with "/openai/v1/"
            api_version: The optional deployment api version. If provided will override the value
                in the env vars or .env file. Currently, the api_version must be "preview".
            ad_token: The Azure Active Directory token. (Optional)
            ad_token_provider: The Azure Active Directory token provider. (Optional)
            token_endpoint: The token endpoint to request an Azure token. (Optional)
            credential: The Azure credential for authentication. (Optional)
            default_headers: The default headers mapping of string keys to
                string values for HTTP requests. (Optional)
            async_client: An existing client to use. (Optional)
            env_file_path: Use the environment settings file as a fallback to using env vars.
            env_file_encoding: The encoding of the environment settings file, defaults to 'utf-8'.
            instruction_role: The role to use for 'instruction' messages, for example, summarization
                prompts could use `developer` or `system`. (Optional)
            kwargs: Additional keyword arguments.
        """
        if model_id := kwargs.pop("model_id", None) and not deployment_name:
            deployment_name = str(model_id)
        try:
            azure_openai_settings = AzureOpenAISettings(
                # pydantic settings will see if there is a value, if not, will try the env var or .env file
                api_key=api_key,  # type: ignore
                base_url=base_url,  # type: ignore
                endpoint=endpoint,  # type: ignore
                responses_deployment_name=deployment_name,
                api_version=api_version,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
                token_endpoint=token_endpoint,
                default_api_version="preview",
            )
            # TODO(peterychang): This is a temporary hack to ensure that the base_url is set correctly
            # while this feature is in preview.
            # But we should only do this if we're on azure. Private deployments may not need this.
            if (
                not azure_openai_settings.base_url
                and azure_openai_settings.endpoint
                and azure_openai_settings.endpoint.host
                and azure_openai_settings.endpoint.host.endswith(".openai.azure.com")
            ):
                azure_openai_settings.base_url = urljoin(str(azure_openai_settings.endpoint), "/openai/v1/")  # type: ignore
        except ValidationError as exc:
            raise ServiceInitializationError(f"Failed to validate settings: {exc}") from exc

        if not azure_openai_settings.responses_deployment_name:
            raise ServiceInitializationError(
                "Azure OpenAI deployment name is required. Set via 'deployment_name' parameter "
                "or 'AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME' environment variable."
            )

        super().__init__(
            deployment_name=azure_openai_settings.responses_deployment_name,
            endpoint=azure_openai_settings.endpoint,
            base_url=azure_openai_settings.base_url,
            api_version=azure_openai_settings.api_version,  # type: ignore
            api_key=azure_openai_settings.api_key.get_secret_value() if azure_openai_settings.api_key else None,
            ad_token=ad_token,
            ad_token_provider=ad_token_provider,
            token_endpoint=azure_openai_settings.token_endpoint,
            credential=credential,
            default_headers=default_headers,
            client=async_client,
            instruction_role=instruction_role,
        )
